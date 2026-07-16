import logging

from grantry.logging_setup import configure_logging, redact


def test_redacts_known_keys():
    text = "accessKeyId=AKIAEXAMPLE secretAccessKey=abc/def+ghiJKL sessionToken=zzzz"
    out = redact(text)
    assert "AKIAEXAMPLE" not in out
    assert "abc/def+ghiJKL" not in out
    assert "zzzz" not in out
    assert "***" in out


def test_redacts_json_shape():
    text = '{"accessToken": "verylongtokenvalue1234567890abcdef", "region": "us-east-1"}'
    out = redact(text)
    assert "verylongtokenvalue1234567890abcdef" not in out
    assert "us-east-1" in out


def test_handler_filter_redacts(capsys):
    configure_logging(verbosity=2)
    logging.getLogger("grantry.test").debug("token=supersecretvalue1234567890abcd")
    err = capsys.readouterr().err
    assert "supersecretvalue1234567890abcd" not in err
