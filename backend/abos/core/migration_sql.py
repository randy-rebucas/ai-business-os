"""SQL helpers shared by Alembic migrations (ADR-003). Keep them stable: old migrations import them.

Every new tenant table (one with `organization_id`) must call `enable_tenant_rls(op, table)` in its migration;
`tests/test_rls.py` fails otherwise.
"""

APP_ROLE = "abos_app"

VISIBLE = ("(current_setting('app.system_scope', true) = 'on' "
           "OR organization_id = nullif(current_setting('app.org_id', true), '')::uuid)")


def create_app_role(op) -> None:
    # NOLOGIN group role; the login user is granted membership and the app does SET ROLE on every connection.
    # In managed Postgres, create the role up front if the migration user lacks CREATEROLE.
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
            END IF;
            BEGIN
                EXECUTE format('GRANT {APP_ROLE} TO %I', current_user);
            EXCEPTION WHEN insufficient_privilege OR invalid_grant_operation THEN
                RAISE NOTICE 'could not grant {APP_ROLE} to %; grant it manually', current_user;
            END;
        END $$;
    """)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}")


def revoke_app_privileges(op) -> None:
    # The role itself stays (other databases on the server, e.g. abos_test, may use it).
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")


def enable_tenant_rls(op, table: str, *, check: str | None = None) -> None:
    # ENABLE (not FORCE): the owner role (migrations, backups) is unaffected; the app never runs as the owner —
    # production refuses to start if its role could bypass RLS (abos.main.lifespan).
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {VISIBLE} WITH CHECK {check or VISIBLE}")


def disable_tenant_rls(op, table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def make_append_only(op, table: str, *, allow_null_fks: tuple[str, ...] = ()) -> None:
    """Reject UPDATE/DELETE at the DB level. FK columns listed in allow_null_fks may only change to NULL (the
    ON DELETE SET NULL cascade when an org or user is deleted)."""
    fn = f"{table}_append_only"
    fk_list = ", ".join(f"'{c}'" for c in allow_null_fks) or "''"
    fk_ok = " AND ".join(f"(NEW.{c} IS NOT DISTINCT FROM OLD.{c} OR NEW.{c} IS NULL)" for c in allow_null_fks) or "TRUE"
    op.execute(f"""
        CREATE FUNCTION {fn}() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION '{table} is append-only';
            END IF;
            -- Every column except the nullable FKs must be unchanged; those may only become NULL.
            IF (to_jsonb(OLD) - ARRAY[{fk_list}]::text[]) IS DISTINCT FROM (to_jsonb(NEW) - ARRAY[{fk_list}]::text[])
               OR NOT ({fk_ok}) THEN
                RAISE EXCEPTION '{table} is append-only';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute(f"CREATE TRIGGER {fn} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {fn}()")
    op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM {APP_ROLE}")


def revoke_rewrite(op, table: str) -> None:
    """The app role may insert and read but never UPDATE/DELETE. Owner-run FK cascades (org deletion) still work,
    unlike a trigger — use this for ledgers that must disappear with their organization."""
    op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM {APP_ROLE}")


def drop_append_only(op, table: str) -> None:
    fn = f"{table}_append_only"
    op.execute(f"DROP TRIGGER IF EXISTS {fn} ON {table}")
    op.execute(f"DROP FUNCTION IF EXISTS {fn}()")


def make_write_once(op, table: str, *, column: str = "status", open_value: str = "started") -> None:
    """Rows are final when inserted, except rows inserted with `column = open_value`, which may be completed by
    exactly one UPDATE (to any other value). DELETE is revoked from the app role; owner-run FK cascades still work."""
    fn = f"{table}_write_once"
    op.execute(f"""
        CREATE FUNCTION {fn}() RETURNS trigger AS $$
        BEGIN
            IF OLD.{column} IS DISTINCT FROM '{open_value}' OR NEW.{column} = '{open_value}' THEN
                RAISE EXCEPTION '{table} rows are write-once';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute(f"CREATE TRIGGER {fn} BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION {fn}()")
    op.execute(f"REVOKE DELETE ON {table} FROM {APP_ROLE}")


def drop_write_once(op, table: str) -> None:
    fn = f"{table}_write_once"
    op.execute(f"DROP TRIGGER IF EXISTS {fn} ON {table}")
    op.execute(f"DROP FUNCTION IF EXISTS {fn}()")
