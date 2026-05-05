"""Compatibility wrapper for :mod:`governance.run_index`."""

from governance.run_index import *  # noqa: F401,F403
from governance.run_index import main


if __name__ == "__main__":
    raise SystemExit(main())
