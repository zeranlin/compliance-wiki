"""Compatibility wrapper for :mod:`governance.compare_f1_runs`."""

from governance.compare_f1_runs import *  # noqa: F401,F403
from governance.compare_f1_runs import main


if __name__ == "__main__":
    raise SystemExit(main())
