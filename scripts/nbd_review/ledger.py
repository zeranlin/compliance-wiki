"""Compatibility wrapper for :mod:`governance.ledger`."""

from governance.ledger import *  # noqa: F401,F403
from governance.ledger import main


if __name__ == "__main__":
    raise SystemExit(main())
