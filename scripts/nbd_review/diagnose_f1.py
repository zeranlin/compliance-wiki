"""Compatibility wrapper for :mod:`governance.diagnose_f1`."""

from governance.diagnose_f1 import *  # noqa: F401,F403
from governance.diagnose_f1 import main


if __name__ == "__main__":
    raise SystemExit(main())
