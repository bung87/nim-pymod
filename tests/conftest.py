import importlib
import pytest


_PMGEN_PY_DIRPATH_DEFAULT = ".."
_PMGEN_PY_FNAME_DEFAULT = "pmgen.py"

def pytest_addoption(parser):
    # http://pytest.readthedocs.org/en/2.0.3/plugins.html#_pytest.hookspec.pytest_addoption

    # Pytest's option parser is similar to Python's stdlib `argparse`:
    #  https://docs.python.org/2/library/argparse.html#argparse.ArgumentParser.add_argument
    pmgen_py_dirpath_help = \
            "override the directory path to the 'pmgen.py' script " + \
            "from the default of '%(default)s'. The path can be specified " + \
            "as a relative path or absolute path."
    parser.addoption("--pmgen_py_dirpath", type="string", metavar="DIRPATH",
            default=_PMGEN_PY_DIRPATH_DEFAULT, action="store", dest="pmgen_py_dirpath",
            help=pmgen_py_dirpath_help)

    pmgen_py_fname_help = \
            "override the filename of the 'pmgen.py' script " + \
            "from the default of '%(default)s'."
    parser.addoption("--pmgen_py_fname", type="string", metavar="FNAME",
            default=_PMGEN_PY_FNAME_DEFAULT, action="store", dest="pmgen_py_fname",
            help=pmgen_py_fname_help)


def _get_option_value(config, option_name, option_default_value):
    cmdline_option_value = config.getoption(option_name)
    if cmdline_option_value and (cmdline_option_value != option_default_value):
        return cmdline_option_value

    inicfg_option_value = config.inicfg.get(option_name)
    if inicfg_option_value and (inicfg_option_value != option_default_value):
        return inicfg_option_value

    return option_default_value


@pytest.fixture(scope="session")
def pmgen_py_fullpath(request):
    pmgen_py_dirpath = _get_option_value(request.config, "pmgen_py_dirpath", _PMGEN_PY_DIRPATH_DEFAULT)
    pmgen_py_fname = _get_option_value(request.config, "pmgen_py_fname", _PMGEN_PY_FNAME_DEFAULT)
    print("\nInitializing test session...")
    print(" - pmgen.py dirpath specified: %s" % pmgen_py_dirpath)
    print(" - pmgen.py fname specified: %s" % pmgen_py_fname)

    # Note that `request.config.invocation_dir` returns a LocalPath instance,
    # not a string.
    #  http://py.readthedocs.org/en/latest/path.html#py._path.local.LocalPath
    invocation_dir = request.config.invocation_dir
    pmgen_py_fullpath = invocation_dir.join(pmgen_py_dirpath, pmgen_py_fname, abs=1)
    print(" - pmgen.py fullpath to use: %s\n" % pmgen_py_fullpath)

    # Test whether the specified fullpath actually exists.
    if pmgen_py_fullpath.stat(raising=False) is None:
        request.raiseerror("file does not exist: %s" % pmgen_py_fullpath)

    return str(pmgen_py_fullpath)


@pytest.fixture(scope="session")
def python_exe_fullpath(request):
    # Determine the fullpath of the Python executable to run
    # (which also tells us the current version of Python).
    # https://docs.python.org/2/library/sys.html#sys.executable
    import sys
    python_exe_path = sys.executable
    if not python_exe_path:
        # "If Python is unable to retrieve the real path to its executable,
        # `sys.executable` will be an empty string or None."
        request.raiseerror("unable to determine real path to Python executable")

    return python_exe_path


@pytest.fixture(scope="module", autouse=True)
def chdir_into_test_dir(request):
    print("\nInitializing test module: %s" % request.module.__name__)

    # Note that `request.config.invocation_dir` returns a LocalPath instance,
    # not a string.
    #  http://py.readthedocs.org/en/latest/path.html#py._path.local.LocalPath
    invocation_dir = request.config.invocation_dir
    print("Test invocation directory: %s" % invocation_dir)

    # Note that `request.fspath` returns a LocalPath instance, not a string.
    #  http://py.readthedocs.org/en/latest/path.html#py._path.local.LocalPath
    #
    # But, dumb API design: `.dirname` returns `str` rather than `LocalPath`.
    # So we have to use `.parts(reverse=True)[1]` instead.
    #test_dir = request.fspath.dirname
    test_dir = request.fspath.parts(reverse=True)[1]
    print("Chdir into test directory: %s" % test_dir)
    prev_dir = test_dir.chdir()

    def chdir_back_to_starting_dir():
        print("Chdir back to previous directory: %s" % prev_dir)
        prev_dir.chdir()
    request.addfinalizer(chdir_back_to_starting_dir)


@pytest.fixture
def pymod_test_mod():
    return importlib.import_module("_pymod_test")
