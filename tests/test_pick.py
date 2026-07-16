from grantry.pick import choose_numbered, choose_with_fzf

KEYS = ["mlp-dev/AWSReadOnlyAccess", "mlp-prod/AWSAdministratorAccess"]


def test_fzf_returns_selected_line():
    def runner(stdin_text):
        assert "mlp-dev/AWSReadOnlyAccess" in stdin_text
        return 0, "mlp-prod/AWSAdministratorAccess\n"

    assert choose_with_fzf(KEYS, runner) == "mlp-prod/AWSAdministratorAccess"


def test_fzf_cancel_returns_none():
    assert choose_with_fzf(KEYS, lambda _s: (130, "")) is None


def test_fzf_rejects_line_not_in_keys():
    assert choose_with_fzf(KEYS, lambda _s: (0, "something-else\n")) is None


def test_numbered_choice_valid():
    written: list[str] = []
    chosen = choose_numbered(KEYS, read_line=lambda: "2", write=written.append)
    assert chosen == "mlp-prod/AWSAdministratorAccess"
    assert any("mlp-dev/AWSReadOnlyAccess" in line for line in written)


def test_numbered_choice_blank_cancels():
    assert choose_numbered(KEYS, read_line=lambda: "", write=lambda s: None) is None


def test_numbered_choice_out_of_range():
    assert choose_numbered(KEYS, read_line=lambda: "9", write=lambda s: None) is None
