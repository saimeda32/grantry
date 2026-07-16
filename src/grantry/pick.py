"""Interactive identity picker. Uses fzf when it is installed for a fuzzy
finder, otherwise falls back to a numbered menu. The selection logic is split
from the IO so it can be tested without a terminal.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable


def choose_with_fzf(
    keys: list[str],
    runner: Callable[[str], tuple[int, str]] | None = None,
) -> str | None:
    """Pipe the keys to fzf and return the chosen line, or None if cancelled.
    runner takes the newline-joined input and returns (returncode, stdout); it
    defaults to invoking fzf.
    """
    if runner is None:
        runner = _fzf_runner
    code, out = runner("\n".join(keys))
    if code != 0:
        return None
    picked = out.strip()
    return picked if picked in keys else None


def _fzf_runner(stdin_text: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["fzf", "--prompt=identity> ", "--height=40%", "--reverse"],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def choose_numbered(
    keys: list[str],
    read_line: Callable[[], str],
    write: Callable[[str], None] = lambda s: print(s, file=sys.stderr),
) -> str | None:
    """Show a numbered menu and return the chosen key, or None on empty/invalid
    input. read_line returns the user's typed choice; write emits the menu.
    """
    for i, key in enumerate(keys, start=1):
        write(f"{i:>3}  {key}")
    write("Choose a number (blank to cancel): ")
    raw = read_line().strip()
    if not raw.isdigit():
        return None
    idx = int(raw)
    if 1 <= idx <= len(keys):
        return keys[idx - 1]
    return None


def choose(keys: list[str]) -> str | None:
    """Pick an identity interactively: fzf if available and attached to a
    terminal, else a numbered menu. Returns None if nothing was chosen.
    """
    if not keys:
        return None
    if shutil.which("fzf") and sys.stdin.isatty():
        return choose_with_fzf(keys)
    if not sys.stdin.isatty():
        return None  # no terminal to prompt on; caller must pass an identity
    return choose_numbered(keys, input)
