"""`python -m abos.jobs sweep` — recover lost/stuck jobs · `python -m abos.jobs tick` — start due scheduled
tasks, emit overdue-invoice events and release deferred runs · `python -m abos.jobs housekeeping` — scheduled
workspace deletions and retention purges (all three are also Celery beat tasks)."""

import json
import sys

from abos import models  # noqa: F401
from abos.jobs import service
from abos.knowledge import ingest  # noqa: F401  (registers job handlers)
from abos.notifications import service as notifications  # noqa: F401  (registers job handlers)
from abos.orchestration import scheduler
from abos.orchestration import service as orchestration  # noqa: F401  (registers job handlers)
from abos.privacy import housekeeping
from abos.simulation import service as simulation  # noqa: F401  (registers job handlers)

COMMANDS = {"sweep": service.sweep, "tick": scheduler.tick, "housekeeping": housekeeping.run}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    print(json.dumps(COMMANDS[sys.argv[1]](), default=str))
