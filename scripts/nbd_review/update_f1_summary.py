"""Compatibility wrapper for :mod:`quality_eval.update_f1_summary`."""

from quality_eval.update_f1_summary import *  # noqa: F401,F403
from quality_eval.update_f1_summary import main


if __name__ == "__main__":
    raise SystemExit(main())
