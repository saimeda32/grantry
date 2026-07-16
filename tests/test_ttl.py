import pytest

from grantry.ttl import format_ttl, parse_ttl


@pytest.mark.parametrize(
    "text,secs",
    [("15m", 900), ("1h", 3600), ("3600s", 3600), ("12h", 43200), ("45s", 45)],
)
def test_parse(text, secs):
    assert parse_ttl(text) == secs


@pytest.mark.parametrize("bad", ["", "15", "m", "1d", "-5m", "1.5h", "abc"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        parse_ttl(bad)


@pytest.mark.parametrize("secs,text", [(900, "15m"), (3600, "1h"), (45, "45s"), (43200, "12h")])
def test_format(secs, text):
    assert format_ttl(secs) == text
