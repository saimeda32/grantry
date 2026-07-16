import grantry


def test_version_is_a_string():
    assert isinstance(grantry.__version__, str)
    assert grantry.__version__
