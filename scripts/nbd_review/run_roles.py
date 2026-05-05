"""Compatibility wrapper for :mod:`quality_eval.run_roles`."""

from quality_eval.run_roles import *  # noqa: F401,F403
from quality_eval.run_roles import main


if __name__ == "__main__":
    raise SystemExit(main())
