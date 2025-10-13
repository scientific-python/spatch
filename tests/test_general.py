import spatch


def test___version__():
    # Sanity check that __version__ exists and returns
    # something that faintly looks like a version string.
    v = spatch.__version__
    major, minor, *rest = v.split(".")
    assert major.isdigit()
    assert minor.isdigit()
