from grantry.pick import choose, choose_numbered, choose_with_fzf

KEYS = ["acme-dev/AWSReadOnlyAccess", "acme-prod/AWSAdministratorAccess"]


def test_fzf_returns_selected_line():
    def runner(stdin_text):
        assert "acme-dev/AWSReadOnlyAccess" in stdin_text
        return 0, "acme-prod/AWSAdministratorAccess\n"

    assert choose_with_fzf(KEYS, runner) == "acme-prod/AWSAdministratorAccess"


def test_fzf_cancel_returns_none():
    assert choose_with_fzf(KEYS, lambda _s: (130, "")) is None


def test_fzf_rejects_line_not_in_keys():
    assert choose_with_fzf(KEYS, lambda _s: (0, "something-else\n")) is None


def test_numbered_choice_valid():
    written: list[str] = []
    chosen = choose_numbered(KEYS, read_line=lambda: "2", write=written.append)
    assert chosen == "acme-prod/AWSAdministratorAccess"
    assert any("acme-dev/AWSReadOnlyAccess" in line for line in written)


def test_numbered_choice_blank_cancels():
    assert choose_numbered(KEYS, read_line=lambda: "", write=lambda s: None) is None


def test_numbered_choice_out_of_range():
    assert choose_numbered(KEYS, read_line=lambda: "9", write=lambda s: None) is None


def test_choose_wraps_numbered_menu_in_alternate_screen(monkeypatch):
    import sys

    writes: list[str] = []
    monkeypatch.setattr("grantry.pick.shutil.which", lambda _x: None)  # no fzf -> numbered
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "write", writes.append)
    monkeypatch.setattr(sys.stderr, "flush", lambda: None)
    monkeypatch.setattr("builtins.input", lambda: "1")

    result = choose(KEYS)
    joined = "".join(writes)
    assert result == "acme-dev/AWSReadOnlyAccess"
    assert "\033[?1049h" in joined  # entered the alternate screen
    assert "\033[?1049l" in joined  # and restored it (menu disappears)
