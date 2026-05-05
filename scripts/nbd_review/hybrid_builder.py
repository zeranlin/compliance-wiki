"""Compatibility wrapper for :mod:`quality_eval.hybrid_builder`."""

from quality_eval.hybrid_builder import *  # noqa: F401,F403
from quality_eval.hybrid_builder import main


if __name__ == "__main__":
    raise SystemExit(main())
