"""Compatibility wrapper for :mod:`quality_eval.export_gold_like`."""

from quality_eval.export_gold_like import *  # noqa: F401,F403
from quality_eval.export_gold_like import main


if __name__ == "__main__":
    raise SystemExit(main())
