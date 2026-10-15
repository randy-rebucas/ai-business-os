"""Pure units (SPEC §9): lifecycle transitions, schedule calculations, configuration validation, templates."""

import copy
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from abos.agents import catalog_v1, design, lifecycle, policy, schedule, validation
from abos.agents.models import AgentInstance
from abos.agents.schemas import AgentConfig, TaskIn
from abos.agents.service import config_hash
from abos.core.errors import AppError
from abos.governance.rules import applies_to, classify, parse_amount

HOURS = {d: {"open": "09:00", "close": "17:00"} for d in ("mon", "tue", "wed", "thu", "fri")}
SPECS = {d["key"]: d for d in catalog_v1.DEFINITIONS}


def profile(**kw):
    base = dict(company_name="Acme Trading", reporting_cadence=None, operating_schedule=HOURS, timezone="Asia/Manila")
    return SimpleNamespace(**(base | kw))


def ctx(key="finance", **kw):
    return validation.Context(spec=SPECS[key], timezone="Asia/Manila", operating_schedule=HOURS, **kw)


def build(key="finance", **kw):
    config, tasks = design.template(SPECS[key], profile(**kw))
    return AgentConfig.model_validate(config), [TaskIn.model_validate(t) for t in tasks]


# ---- catalog ---------------------------------------------------------------------------------------------------

def test_catalog_has_agents_a_to_h_with_every_profile_field():
    assert [d["letter"] for d in catalog_v1.DEFINITIONS] == list("ABCDEFGH")
    required = {"name", "department", "expertise", "role_description", "responsibilities", "prohibited",
                "required_knowledge", "tools", "permission_ceilings", "escalation_conditions", "kpis",
                "reporting_frequency", "model", "default_monthly_budget_usd", "default_operating_mode", "tasks"}
    for d in catalog_v1.DEFINITIONS:
        assert required <= set(d), d["key"]
        assert set(d["permission_ceilings"]) == set(policy.SCOPES)
        for scope, ceiling in d["permission_ceilings"].items():
            assert policy.within(ceiling, policy.platform_ceiling(scope)), (d["key"], scope)
        assert set(t["scope"] for t in d["tools"]) <= set(policy.SCOPES)
        assert set(d["supported_events"]) <= set(policy.EVENTS)


def test_no_agent_may_approve_transactions_or_pay_unattended():
    for d in catalog_v1.DEFINITIONS:
        assert d["permission_ceilings"]["transactions.approve"] == "denied"
        assert d["permission_ceilings"]["finance.execute"] != "auto"
    assert SPECS["finance"]["permission_ceilings"]["finance.execute"] == "denied"  # never issues payments


@pytest.mark.parametrize("key", list(SPECS))
def test_every_template_is_valid_for_a_normal_company(key):
    config, tasks = build(key)
    issues = validation.check(config, tasks, ctx(key))
    assert not validation.has_errors(issues), [i.message for i in issues]
    assert not [i for i in issues if i.field == "automation_level"]  # templates don't contradict themselves


def test_template_fits_tasks_into_business_hours():
    notes: list[str] = []
    config, tasks = design.template(SPECS["executive"], profile(), notes)
    briefing = next(t for t in tasks if t["key"] == "daily-briefing")
    assert briefing["trigger"]["schedule"]["time"] == "09:00"  # catalog says 08:00; the company opens at 09:00
    assert notes and "moved to 09:00" in notes[0]
    _, ops_tasks = design.template(SPECS["operations"], profile(), [])
    summary = next(t for t in ops_tasks if t["key"] == "daily-ops-summary")
    assert summary["trigger"]["schedule"]["time"] == "16:00"  # 17:00 is closing time


def test_template_uses_company_reporting_cadence():
    config, _ = design.template(SPECS["finance"], profile(reporting_cadence="weekly"))
    assert config["reporting"]["cadence"] == "weekly"


def test_template_permissions_never_exceed_ceilings():
    for key, spec in SPECS.items():
        config, _ = design.template(spec, profile())
        for scope, mode in config["permissions"].items():
            assert policy.within(mode, spec["permission_ceilings"][scope]), (key, scope)
            assert policy.within(mode, policy.DEFAULT_MODE[scope])


# ---- validation ------------------------------------------------------------------------------------------------

def test_permission_above_definition_ceiling_is_an_error():
    config, tasks = build()
    config.permissions["comms.external"] = "auto"  # finance ceiling: approval_required
    issues = validation.check(config, tasks, ctx())
    assert any(i.field == "permissions.comms.external" and i.severity == "error" for i in issues)


def test_platform_ceiling_beats_definition():
    config, tasks = build("sales")
    config.permissions["transactions.approve"] = "approval_required"  # platform: denied for every AI
    issues = validation.check(config, tasks, ctx("sales"))
    assert any("can never be" in i.message for i in issues)


def test_task_needing_approval_scope_must_be_marked():
    config, tasks = build()
    config.permissions["records.draft"] = "approval_required"
    tasks[0].approval_required = False
    issues = validation.check(config, tasks, ctx())
    assert any(i.field == "tasks[0].approval_required" for i in issues)


def test_task_with_denied_permission_is_an_error():
    config, tasks = build()
    tasks[0].required_permissions = ["data.read", "comms.external"]
    config.permissions["comms.external"] = "denied"
    issues = validation.check(config, tasks, ctx())
    assert any("which is denied" in i.message for i in issues)


def test_schedule_outside_business_hours_is_an_error():
    config, tasks = build()
    tasks[0].trigger.schedule.time = "18:30"
    issues = validation.check(config, tasks, ctx())
    assert any("outside business hours" in i.message for i in issues)
    # The same time is fine when the agent may work at any time.
    config.operating.execution_window = "any_time"
    config.operating.monitoring = "continuous"
    config.operating.mode = "always_on"
    assert not any("outside business hours" in i.message for i in validation.check(config, tasks, ctx()))


def test_business_hours_need_company_hours_and_timezone():
    config, tasks = build()
    c = validation.Context(spec=SPECS["finance"], timezone=None, operating_schedule=None)
    messages = [i.message for i in validation.check(config, tasks, c) if i.severity == "error"]
    assert any("time zone" in m for m in messages)
    assert any("operating days and hours" in m for m in messages)


def test_dependency_cycles_unknown_and_self_references():
    config, tasks = build()
    a, b, c = tasks
    a.depends_on, b.depends_on = [c.key], [a.key]
    c.depends_on = [b.key, "ghost", c.key]
    messages = [i.message for i in validation.check(config, tasks, ctx())]
    assert any("cycle" in m for m in messages)
    assert any("unknown task" in m for m in messages)
    assert any("depend on itself" in m for m in messages)


def test_unsupported_event_and_unconfirmed_policy_ref():
    config, tasks = build()
    tasks[1].trigger.event = "ticket.created"  # a support event, not a finance one
    tasks[0].policy_refs = [uuid.uuid4()]
    messages = [i.message for i in validation.check(config, tasks, ctx())]
    assert any("can't react to" in m for m in messages)
    assert any("isn't confirmed" in m for m in messages)
    ref = tasks[0].policy_refs[0]
    ok = validation.check(config, tasks, ctx(confirmed_rule_ids={str(ref)}))
    assert not any("isn't confirmed" in i.message for i in ok)


def test_sensitive_documents_need_the_scope_and_tools_need_their_scope():
    config, tasks = build("hr")
    config.knowledge.access_levels = ["general", "confidential"]
    config.job.authorized_tools = ["hr_docs.read", "made.up"]
    messages = [i.message for i in validation.check(config, tasks, ctx("hr"))]
    assert any("Restricted or confidential documents" in m for m in messages)
    assert any("Unknown tool" in m for m in messages)
    assert any("which is denied" in m for m in messages)


def test_budget_over_company_budget_is_a_warning_only_in_usd():
    config, tasks = build()
    issues = validation.check(config, tasks, ctx(company_budget=Decimal(100), other_agents_budget=Decimal(50)))
    assert any(i.severity == "warning" and i.field == "limits.monthly_budget_usd" for i in issues)
    issues = validation.check(config, tasks, ctx(company_budget=Decimal(100), company_currency="PHP",
                                                 other_agents_budget=Decimal(500)))
    assert not any(i.field == "limits.monthly_budget_usd" for i in issues)


def test_structural_validation_rejects_bad_tasks():
    good = copy.deepcopy(SPECS["finance"]["tasks"][0])
    for bad in ({"key": "Bad Key"}, {"trigger": {"type": "schedule"}}, {"trigger": {"type": "event", "event": "x"}},
                {"trigger": {"type": "schedule", "schedule": {"kind": "weekly", "days": ["mon"], "time": "25:00"}}},
                {"trigger": {"type": "schedule", "schedule": {"kind": "monthly", "day": 31, "time": "09:00"}}},
                {"required_permissions": ["root.everything"]}, {"failure": {"max_retries": 50}}):
        with pytest.raises(ValueError):
            TaskIn.model_validate(good | bad)


def test_missing_scopes_default_to_denied():
    config, _ = build()
    data = config.model_dump()
    data["permissions"] = {"data.read": "auto"}
    parsed = AgentConfig.model_validate(data)
    assert parsed.permissions["finance.execute"] == "denied" and len(parsed.permissions) == len(policy.SCOPES)


def test_config_hash_is_canonical_and_sensitive():
    config, tasks = build()
    h = config_hash(config, tasks)
    assert h == config_hash(config, list(reversed(tasks)))  # task order doesn't matter
    config.limits.monthly_budget_usd = Decimal("61.00")
    assert config_hash(config, tasks) != h


# ---- lifecycle -------------------------------------------------------------------------------------------------

def instance(status="selected", current=None, approved=None):
    return AgentInstance(status=status, current_config_id=current, approved_config_id=approved)


def test_lifecycle_happy_path_and_terminal_retired():
    c = uuid.uuid4()
    inst = instance()
    for target in ("configuring", "awaiting_approval"):
        lifecycle.transition(inst, target)
    inst.current_config_id = inst.approved_config_id = c
    for target in ("testing", "ready_for_deployment", "active", "paused", "active", "retired"):
        lifecycle.transition(inst, target)
    with pytest.raises(AppError) as e:
        lifecycle.transition(inst, "configuring")
    assert e.value.code == "invalid_transition"


@pytest.mark.parametrize("start,target", [("selected", "active"), ("selected", "awaiting_approval"),
                                          ("configuring", "testing"), ("awaiting_approval", "active"),
                                          ("testing", "active"), ("failed", "active")])
def test_lifecycle_rejects_skipping_steps(start, target):
    with pytest.raises(AppError):
        lifecycle.transition(instance(start, uuid.uuid4(), None), target)


def test_execution_states_require_the_current_config_to_be_approved():
    old, new = uuid.uuid4(), uuid.uuid4()
    inst = instance("awaiting_approval", current=new, approved=old)  # an older version was approved
    with pytest.raises(AppError) as e:
        lifecycle.transition(inst, "testing")
    assert e.value.code == "approval_required"
    for status in ("selected", "configuring", "awaiting_approval", "testing", "ready_for_deployment", "active",
                   "paused", "failed", "retired"):
        assert status in lifecycle.TRANSITIONS


# ---- schedules -------------------------------------------------------------------------------------------------

MANILA = "Asia/Manila"  # UTC+8, no DST


def test_weekly_runs_in_company_timezone_skipping_holidays():
    after = datetime(2026, 12, 23, 0, 0, tzinfo=UTC)  # Wed 08:00 Manila
    runs = schedule.next_runs({"kind": "weekly", "days": ["mon", "tue", "wed", "thu", "fri"], "time": "16:00"},
                              tz=MANILA, after=after, n=3, operating_schedule=HOURS,
                              holidays={date(2026, 12, 25)})
    assert [r.isoformat() for r in runs] == ["2026-12-23T08:00:00+00:00", "2026-12-24T08:00:00+00:00",
                                             "2026-12-28T08:00:00+00:00"]  # Fri 25th (holiday) skipped


def test_weekly_any_time_window_ignores_hours():
    after = datetime(2026, 12, 23, 0, 0, tzinfo=UTC)
    runs = schedule.next_runs({"kind": "weekly", "days": ["sat"], "time": "22:00"}, tz=MANILA, after=after, n=1,
                              window="any_time", operating_schedule=HOURS)
    assert runs == [datetime(2026, 12, 26, 14, 0, tzinfo=UTC)]
    assert schedule.next_runs({"kind": "weekly", "days": ["sat"], "time": "22:00"}, tz=MANILA, after=after, n=1,
                              operating_schedule=HOURS) == []  # never inside business hours


def test_monthly_on_a_holiday_is_deferred_not_dropped():
    after = datetime(2026, 12, 15, tzinfo=UTC)
    runs = schedule.next_runs({"kind": "monthly", "day": 1, "time": "10:00"}, tz=MANILA, after=after, n=2,
                              operating_schedule=HOURS, holidays={date(2027, 1, 1)})
    # Jan 1 2027 is a Friday holiday → next opening Mon Jan 4 09:00 Manila; Feb 1 2027 is a Monday.
    assert runs == [datetime(2027, 1, 4, 1, 0, tzinfo=UTC), datetime(2027, 2, 1, 2, 0, tzinfo=UTC)]


def test_defer_to_business_hours():
    tz, hol = MANILA, set()
    fri_evening = datetime(2026, 12, 18, 11, 0, tzinfo=UTC)  # Fri 19:00 Manila
    assert schedule.defer_to_business_hours(fri_evening, tz, HOURS, hol) == datetime(2026, 12, 21, 1, 0, tzinfo=UTC)
    early = datetime(2026, 12, 21, 0, 0, tzinfo=UTC)  # Mon 08:00 Manila
    assert schedule.defer_to_business_hours(early, tz, HOURS, hol) == datetime(2026, 12, 21, 1, 0, tzinfo=UTC)
    inside = datetime(2026, 12, 21, 3, 0, tzinfo=UTC)
    assert schedule.defer_to_business_hours(inside, tz, HOURS, hol) == inside
    assert schedule.defer_to_business_hours(inside, tz, {}, hol) is None


def test_dst_zone_keeps_local_wall_time():
    after = datetime(2026, 3, 6, tzinfo=UTC)
    runs = schedule.next_runs({"kind": "weekly", "days": ["mon"], "time": "09:00"}, tz="America/New_York",
                              after=after, n=2, window="any_time")
    assert [r.hour for r in runs] == [13, 13]  # 09:00 EDT (after the Mar 8 switch) = 13:00 UTC both weeks
    runs = schedule.next_runs({"kind": "weekly", "days": ["fri"], "time": "09:00"}, tz="America/New_York",
                              after=after, n=2, window="any_time")
    assert [r.hour for r in runs] == [14, 13]  # Fri Mar 6 EST, Fri Mar 13 EDT


# ---- rule parsing ----------------------------------------------------------------------------------------------

def test_parse_amount_needs_a_currency_marker():
    assert parse_amount("refunds above 5,000 PHP need approval") == (Decimal("5000"), "PHP")
    assert parse_amount("anything over $1,250.50 is escalated") == (Decimal("1250.50"), "USD")
    assert parse_amount("₱20,000 limit") == (Decimal("20000"), "PHP")
    assert parse_amount("within 30 days") is None


def test_classify_and_applies_to():
    assert classify("Refunds above 5,000 PHP require written approval from the Finance Manager.") == "threshold"
    assert classify("Disputed charges must be escalated to the Finance Manager within 2 business days.") == "escalation"
    assert classify("Requests need manager approval 7 days ahead.") == "approval"
    assert set(applies_to("Refunds above 5,000 PHP require written approval")) >= {"finance", "support"}
    assert applies_to("Employees receive 15 days of paid annual leave") == ["hr"]
