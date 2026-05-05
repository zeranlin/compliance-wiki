"""Compatibility wrapper for :mod:`quality_eval.evaluate_f1`."""

from quality_eval.evaluate_f1 import *  # noqa: F401,F403
from quality_eval.evaluate_f1 import main


if __name__ == "__main__":
    main()
