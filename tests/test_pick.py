from grantry.pick import (
    choose_numbered,
    choose_with_fzf,
    interactive_select,
    match,
)

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


def test_match_filters_case_insensitively_and_and():
    keys = ["acme-dev/AWSReadOnlyAccess", "acme-prod/AWSAdministratorAccess", "sandbox/PowerUser"]
    assert match(keys, "") == keys  # empty query keeps everything
    assert match(keys, "prod") == ["acme-prod/AWSAdministratorAccess"]
    assert match(keys, "ACME read") == ["acme-dev/AWSReadOnlyAccess"]  # AND, case-insensitive
    assert match(keys, "nomatch") == []


def test_interactive_select_types_to_filter_then_picks():
    # Type "prod", then Enter selects the single match.
    script = iter(["p", "r", "o", "d", "enter"])
    result = interactive_select(KEYS, read_key=lambda: next(script), render=lambda *a: None)
    assert result == "acme-prod/AWSAdministratorAccess"


def test_interactive_select_arrows_move_selection():
    # No filter; arrow down once then Enter picks the second item.
    script = iter(["down", "enter"])
    result = interactive_select(KEYS, read_key=lambda: next(script), render=lambda *a: None)
    assert result == "acme-prod/AWSAdministratorAccess"


def test_interactive_select_esc_cancels():
    script = iter(["esc"])
    assert interactive_select(KEYS, read_key=lambda: next(script), render=lambda *a: None) is None


def test_interactive_select_backspace_widens():
    # Type "xzy" (no match), backspace thrice, then "prod" narrows to one.
    script = iter(
        ["x", "z", "y", "backspace", "backspace", "backspace", "p", "r", "o", "d", "enter"]
    )
    result = interactive_select(KEYS, read_key=lambda: next(script), render=lambda *a: None)
    assert result == "acme-prod/AWSAdministratorAccess"
