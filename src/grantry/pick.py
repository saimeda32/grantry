"""Interactive identity picker.

Order of preference when attached to a terminal:
1. fzf, if installed, for a full fuzzy finder.
2. A built-in live filter: type to narrow the list, arrows to move, Enter to pick.
3. A plain numbered menu, when raw-mode terminal input is not available.

The selection logic is split from the terminal IO so it can be tested without a
real terminal.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable


def choose_with_fzf(
    keys: list[str],
    runner: Callable[[str], tuple[int, str]] | None = None,
) -> str | None:
    """Pipe the keys to fzf and return the chosen line, or None if cancelled."""
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


def match(keys: list[str], query: str) -> list[str]:
    """Case-insensitive, space-separated AND substring filter, order preserved."""
    terms = query.lower().split()
    if not terms:
        return list(keys)
    return [k for k in keys if all(t in k.lower() for t in terms)]


def interactive_select(
    keys: list[str],
    read_key: Callable[[], str],
    render: Callable[[str, list[str], int], None],
) -> str | None:
    """Drive a live-filter picker. read_key() returns one of 'enter', 'esc',
    'up', 'down', 'backspace', or a single character. render(query, filtered,
    selected) draws the current state. Returns the chosen key or None.
    """
    query = ""
    sel = 0
    while True:
        filtered = match(keys, query)
        if sel >= len(filtered):
            sel = max(0, len(filtered) - 1)
        render(query, filtered, sel)
        key = read_key()
        if key == "enter":
            return filtered[sel] if filtered else None
        if key == "esc":
            return None
        if key == "up":
            sel = max(0, sel - 1)
        elif key == "down":
            sel = min(max(0, len(filtered) - 1), sel + 1)
        elif key == "backspace":
            query = query[:-1]
            sel = 0
        elif len(key) == 1 and key >= " ":
            query += key
            sel = 0


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


def _termios_read_key(fd: int) -> str:
    """Read one logical key from a raw-mode terminal."""
    ch = os.read(fd, 1)
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch == b"\x03":  # Ctrl-C
        raise KeyboardInterrupt
    if ch in (b"\x7f", b"\x08"):
        return "backspace"
    if ch == b"\x1b":  # ESC, possibly the start of an arrow sequence
        seq = os.read(fd, 2)
        if seq == b"[A":
            return "up"
        if seq == b"[B":
            return "down"
        return "esc"
    return ch.decode("utf-8", "ignore")


def _render_live(query: str, filtered: list[str], sel: int) -> None:
    rows = max(3, shutil.get_terminal_size((80, 24)).lines - 3)
    out = ["\033[H\033[J", "  type to filter, arrows to move, Enter to pick, Esc to cancel\r\n"]
    out.append(f"\033[36m>\033[0m {query}\r\n")
    shown = filtered[:rows]
    for i, key in enumerate(shown):
        if i == sel:
            out.append(f"\033[7m > {key} \033[0m\r\n")
        else:
            out.append(f"   {key}\r\n")
    if not shown:
        out.append("   (no matches)\r\n")
    elif len(filtered) > len(shown):
        out.append(f"   ... {len(filtered) - len(shown)} more, keep typing to narrow\r\n")
    sys.stderr.write("".join(out))
    sys.stderr.flush()


class _NoRawMode(Exception):
    """Raised when the terminal cannot be put into raw mode for the live picker."""


def _choose_live(keys: list[str]) -> str | None:
    """Live-filter picker in the terminal's alternate screen. Returns the chosen
    key, or None if the user cancelled. Raises _NoRawMode when raw-mode input is
    unavailable (e.g. Windows), so the caller can fall back to the numbered menu.
    """
    try:
        import termios
        import tty
    except ImportError as e:
        raise _NoRawMode from e
    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error as e:
        raise _NoRawMode from e
    sys.stderr.write("\033[?1049h")
    sys.stderr.flush()
    try:
        tty.setraw(fd)
        return interactive_select(keys, lambda: _termios_read_key(fd), _render_live)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stderr.write("\033[?1049l")
        sys.stderr.flush()


def choose(keys: list[str]) -> str | None:
    """Pick an identity interactively. Returns None if nothing was chosen."""
    if not keys:
        return None
    if not sys.stdin.isatty():
        return None  # no terminal to prompt on; caller must pass an identity
    if shutil.which("fzf"):
        return choose_with_fzf(keys)
    if sys.stderr.isatty():
        try:
            # A returned value (even None for cancel) is final; only a missing
            # raw mode falls through to the numbered menu.
            return _choose_live(keys)
        except _NoRawMode:
            pass
    return choose_numbered(keys, input)
