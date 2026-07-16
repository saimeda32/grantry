"""Enable `python -m grantry`, which the MCP config points at so it works
regardless of PATH."""

from grantry.cli import main

raise SystemExit(main())
