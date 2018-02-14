#!/usr/bin/env python

# Copyright (c) 2015 SnapDisco Pty Ltd, Australia.
# All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# [ MIT license: https://opensource.org/licenses/MIT ]

# Usage:
#  python pmgen.py nimmodule.nim

# The original intention of "pmgen.py" was simply to auto-generate Makefiles
# for the Pymod build process (to ensure that the phases of Pymod compilation
# were invoked in the correct order, with the appropriate compiler flags).
# It was implemented in Python purely because Python was more convenient for
# string-munging & for-looping than Unix utilities.
#
# Since then, we've discovered a significant, unplanned benefit of "pmgen.py":
# We can now use the Python instance that's executing "pmgen.py" to determine
# the actual Python system settings, to configure the appropriate Python C-API
# build settings (including those for Numpy).  We can then write these settings
# out to "pmgen/nim.cfg" and the appropriate Makefiles.

from __future__ import print_function

import datetime
import glob
import os
import re
#import shutil
import subprocess
import sys
import argparse
import textwrap

from .usefulconfigparser import UsefulConfigParser


NIM_COMPILER_EXE_PATH = "nim"
NIM_COMPILER_FLAGS = []
NIM_COMPILER_FLAG_OPTIONS = dict(
        nimSetIsRelease=["-d:release"],
)
NIM_COMPILER_COMMAND = "%s %%s %s" % (NIM_COMPILER_EXE_PATH, " ".join(NIM_COMPILER_FLAGS))

# For the Makefiles.
NIM_DEFINED_SYMBOLS_MAKE = "pmgen".split()
NIM_SYMBOL_DEFS_MAKE = " ".join("--define:%s" % s for s in NIM_DEFINED_SYMBOLS_MAKE)


MAKE_EXE_PATH = "make"

NUMPY_C_INCLUDE_RELPATH = "core/include"


NIM_CFG_FNAME = "nim.cfg"
NIM_CFG_CONTENT = """# Auto-generated by "pmgen.py" on %(datestamp)s.
# Any changes will be overwritten by the next run of "pmgen.py".
%(python_cincludes)s
%(nim_symbol_defs)s
listCmd
nimcache:"nimcache"
parallelBuild:"1"
passC:"-Wall -O3 -fPIC"
passL:"-O3 %(python_ldflags)s -fPIC"
%(any_other_module_paths)s
verbosity:"2"
"""


PMGEN_DIRNAME = "pmgen"
PMGEN_PREFIX = "pmgen"
PMGEN_RULE_TARGET = "pmgen"

MAKEFILE_FNAME_TEMPLATE = "Makefile.pmgen-%s"
MAKEFILE_PMGEN_VARIABLE = """PMGEN = %s %%s --noLinking --noMain""" % NIM_SYMBOL_DEFS_MAKE
MAKEFILE2_FNAME_TEMPLATE = "Makefile"

MAKEFILE_CLEAN_RULES = """allclean: clean soclean

soclean:
\trm -f *.so

clean:
\trm -rf nimcache
\trm -f nim.cfg
\trm -f %(pmgen_prefix)s*_capi.c
\trm -f %(pmgen_prefix)s*_incl.nim
\trm -f %(pmgen_prefix)s*_wrap.nim
\trm -f %(pmgen_prefix)s*_wrap.nim.cfg
"""
MAKEFILE_CONTENT = """# Auto-generated by "pmgen.py" on %(datestamp)s.
# Any changes will be overwritten by the next run of "pmgen.py".

%(variables)s

%(build_rules)s

%(clean_rules)s
"""


PMINC_FNAME_TEMPLATE = "%(pmgen_prefix)s%(modname_basename)s_incl.nim"
PMINC_CONTENT = """# Auto-generated by "pmgen.py" on %(datestamp)s.
# Any changes will be overwritten by the next run of "pmgen.py".

# These must be included rather than imported, so the static global variables
# can be evaluated at compile time.
include pymodpkg/private/includes/realmacrodefs

include pymodpkg/private/includes/pyobjecttypedefs

# Modules to be imported by the auto-generated Nim wrappers.
%(imports)s

# Modules to be included into this Nim code, so their procs can be exportpy'd.
%(includes)s
"""
def parse_args():
    parser = argparse.ArgumentParser( prog = 'pmgen',
                                      formatter_class = argparse.RawDescriptionHelpFormatter,
                                      description = textwrap.dedent(
                                      'useage:pmgen nimmodule.nim')
                                    )
    parser.add_argument('infiles', nargs="+",type=str)
    parser.add_argument('--pymodName', dest="pymodName", default=None,
                        metavar="string", action='store', type=str)
    # parser.add_argument('--numpyEnabled', dest="numpyEnabled", default=False,
    #                     action='store_true')
    parser.add_argument('--pyarrayEnabled', dest="pyarrayEnabled", default=False,
                        action='store_true')

    parser.add_argument('--release', dest="release", default=False,
                        action='store_true')

    args, unknown = parser.parse_known_args()
    return args, unknown

def main():
    # For the "nim.cfg".
    nim_defined_symbols_cfg = ["pymodEnabled"]
    args, unknown = parse_args()
    
    if args.pymodName:
        nim_defined_symbols_cfg.append("pymodName=%s" % args.pymodName) 

    # if args.numpyEnabled:
    #     nim_defined_symbols_cfg.append("numpyEnabled") 

    if args.pyarrayEnabled:
        nim_defined_symbols_cfg.append("pyarrayEnabled") 

    nim_symbol_defs_cfg = "\n".join("define:\"%s\"" % s for s in nim_defined_symbols_cfg)

    (nim_modfiles, nim_modnames) = get_nim_modnames_as_relpaths(args.infiles)
    if len(nim_modnames) < 1:
        die("no Nim module names specified")

    global CONFIG
    CONFIG = readPymodConfig()
    global NIM_COMPILER_COMMAND
    NIM_COMPILER_COMMAND = getCompilerCommand(args)

    orig_dir = os.getcwd()
    if not (os.path.exists(PMGEN_DIRNAME) and os.path.isdir(PMGEN_DIRNAME)):
        os.mkdir(PMGEN_DIRNAME)
    os.chdir(PMGEN_DIRNAME)

    (python_includes, python_ldflags) = determine_python_includes_ldflags()
    numpy_paths = test_that_numpy_is_installed()
    generate_nim_cfg_file( args,nim_symbol_defs_cfg,python_includes, python_ldflags, numpy_paths)
    pminc_basename = generate_pminc_file(args,nim_modnames)

    generate_pmgen_files(args,nim_modfiles, pminc_basename)

    # FIXME:  This approach (of simply globbing by filenames) is highly dodgy.
    # Work out a better way of doing this.
    nim_wrapper_glob = "%(pmgen_prefix)s*_wrap.nim" % dict(
            pmgen_prefix=PMGEN_PREFIX)
    nim_wrapper_fnames = glob.glob(nim_wrapper_glob)

    pymodule_fnames = extract_pymodule_fnames_from_glob(nim_wrapper_fnames,
            nim_wrapper_glob)

    python_exe_name = sys.executable
    compile_generated_nim_wrappers(nim_wrapper_fnames, pymodule_fnames,
            nim_modfiles, pminc_basename, python_exe_name)
    #for pymodule_fname in pymodule_fnames:
    #    shutil.copyfile(pymodule_fname, os.path.join("..", pymodule_fname))

    os.chdir(orig_dir)


def getCompilerCommand(args):
    nim_compiler_flags = NIM_COMPILER_FLAGS[:]
    if  args.release or any(CONFIG.getboolean("all", "nimSetIsRelease")):
        nim_compiler_flags.extend(NIM_COMPILER_FLAG_OPTIONS["nimSetIsRelease"])
        #print("nimSetIsRelease: True")

    cmd = "%s %%s %s" % (NIM_COMPILER_EXE_PATH, " ".join(nim_compiler_flags))
    #print("Nim compiler command:", cmd)
    return cmd


def readPymodConfig():
    c = UsefulConfigParser()
    cfg_files_read = c.read("pymod.cfg")
    return c


def get_nim_modnames_as_relpaths(cmdline_args):
    nim_modfiles = []
    nim_modnames = []
    for arg in cmdline_args:
        if arg.endswith(".nim"):
            if os.path.exists(arg):
                nim_modfiles.append(os.path.relpath(arg))
                nim_modnames.append(os.path.relpath(arg[:-4]))
            else:
                die("file not found: %s" % arg)
        else:  # not arg.endswith(".nim")
            if os.path.exists(arg + ".nim"):
                nim_modfiles.append(os.path.relpath(arg + ".nim"))
                nim_modnames.append(os.path.relpath(arg))
            else:
                die("file not found: %s.nim" % arg)

    return (nim_modfiles, nim_modnames)


def extract_pymodule_fnames_from_glob(nim_wrapper_fnames, nim_wrapper_glob):
    nim_wrapper_pattern = nim_wrapper_glob.replace("*", "(.+)")
    regex = re.compile(nim_wrapper_pattern)
    pymodule_fnames = [
            "%s.so" % regex.match(wrapper_fname).group(1)
            for wrapper_fname in nim_wrapper_fnames]
    return pymodule_fnames


def get_datestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d at %H:%M:%S")


def generate_nim_cfg_file(args,nim_symbol_defs_cfg,python_includes, python_ldflags, numpy_paths):
    datestamp = get_datestamp()

    any_other_module_paths = []
    for optval in CONFIG.get("all", "nimAddModulePath"):
        path = stripAnyQuotes(optval)
        if not path.startswith("/"):
            # It's a relative path rather than an absolute path.
            # Since it's relative to the parent directory, it needs to
            # be updated because we are now in the "pmgen" directory.
            path = dotdot(path)
        path = os.path.realpath(path)
        any_other_module_paths.append('path:"%s"' % path)
    #print("nimAddModulePath:", any_other_module_paths)
    if args.pyarrayEnabled:
        numpy_include_paths = [os.path.join(p, NUMPY_C_INCLUDE_RELPATH) for p in numpy_paths]
        numpy_includes = ["-I" + p for p in numpy_include_paths if os.path.isdir(p)]
        print("Determined Numpy C-API includes\n - includes = %s" % numpy_includes)
        python_includes.extend(numpy_includes)

    python_includes_uniq = sorted([
            # Remove the leading "-I", if present.
            ipath[2:] if ipath.startswith("-I") else ipath
            for ipath in set(python_includes)])

    python_cincludes = "\n".join([
            'cincludes:"%s"' % path
            for path in python_includes_uniq])

    pymod_path = subprocess.check_output("nimble path pymod| tail -n 1",shell=True).decode("UTF-8").strip()
    if not os.path.isdir(pymod_path):
        die("Can not find pymodpkg through nimble")

    python_cincludes += '\ncincludes: "' + pymod_path + '"'

    python_ldflags = " ".join(python_ldflags)
    any_other_module_paths = "\n".join(any_other_module_paths)

    with open(NIM_CFG_FNAME, "w") as f:
        f.write(NIM_CFG_CONTENT % dict(
                datestamp=datestamp,
                python_cincludes=python_cincludes,
                nim_symbol_defs=nim_symbol_defs_cfg,
                python_ldflags=python_ldflags,
                any_other_module_paths=any_other_module_paths))


def stripAnyQuotes(s):
    if s.startswith('"""') and s.endswith('"""'):
        return s[3:-3]
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def dotdot(relpath):
    # Assumes that `relpath` is a relative path that was obtained from the
    # command-line arguments by the function `get_nim_modnames_as_relpaths`.
    return os.path.join("..", relpath)


def generate_pminc_file(args,nim_modnames):
    datestamp = get_datestamp()

    # We need to "dot-dot" one level, because we are in the "pmgen" subdir.
    nim_modnames = [dotdot(modname) for modname in nim_modnames]
    register_to_import = ["registerNimModuleToImport(\"%s\")" % modname
            for modname in nim_modnames]
    includes = ["include %s" % modname for modname in nim_modnames]

    last_nim_modname_basename = args.pymodName if args.pymodName else os.path.basename(nim_modnames[-1])

    pminc_fname = PMINC_FNAME_TEMPLATE % dict(
            modname_basename=last_nim_modname_basename,
            pmgen_prefix=PMGEN_PREFIX)
    with open(pminc_fname, "w") as f:
        f.write(PMINC_CONTENT % dict(
                datestamp=datestamp,
                imports="\n".join(register_to_import),
                # Leave an empty line between each include.
                includes="\n\n".join(includes)))

    return last_nim_modname_basename


def generate_pmgen_files(args,nim_modfiles, pminc_basename):
    datestamp = get_datestamp()

    # Create the Makefile.
    rule_target = PMGEN_RULE_TARGET
    pminc_fname = PMINC_FNAME_TEMPLATE % dict(
            modname_basename=pminc_basename,
            pmgen_prefix=PMGEN_PREFIX)
    # We need to "dot-dot" one level, because we are in the "pmgen" subdir.
    nim_modfiles = [dotdot(modfname) for modfname in nim_modfiles]
    prereqs = [pminc_fname] + nim_modfiles

    compile_rule = "%s: %s\n\t%s $(PMGEN) %s" % \
            (rule_target, " ".join(prereqs), NIM_COMPILER_COMMAND % "compile", pminc_fname)

    makefile_fname = MAKEFILE_FNAME_TEMPLATE % pminc_basename
    makefile_clean_rules = MAKEFILE_CLEAN_RULES % dict(
            pmgen_prefix=PMGEN_PREFIX)
    with open(makefile_fname, "w") as f:
        f.write(MAKEFILE_CONTENT % dict(
                datestamp=datestamp,
                variables=MAKEFILE_PMGEN_VARIABLE % define_python3_maybe(),
                build_rules=compile_rule,
                clean_rules=makefile_clean_rules))

    make_command = [MAKE_EXE_PATH, "-f", makefile_fname, rule_target]
    print(" ".join(make_command))
    subprocess.check_call(make_command)


def compile_generated_nim_wrappers(nim_wrapper_fnames, pymodule_fnames,
        nim_modfiles, pminc_basename, python_exe_name):
    datestamp = get_datestamp()

    # Create the Makefile.
    # We need to "dot-dot" one level, because we are in the "pmgen" subdir.
    nim_modfiles_rel_pmgen_dir = [dotdot(modfname) for modfname in nim_modfiles]

    script_cmd = sys.argv[0]
    if os.path.isabs(script_cmd):
        abspath_to_pmgen_py = script_cmd
    else:
        abspath_to_pmgen_py = os.path.abspath(dotdot(script_cmd))

    pminc_fname = PMINC_FNAME_TEMPLATE % dict(
            modname_basename=pminc_basename,
            pmgen_prefix=PMGEN_PREFIX)
    build_rules = [
            "all: %s" % " ".join(pymodule_fnames)
            ] + [
            "%s: %s\n\t%s %s\n\tmv -f %s ../" %
                    (pymodule_fname, nim_fname, NIM_COMPILER_COMMAND % "compile", nim_fname,
                            pymodule_fname)
            for nim_fname, pymodule_fname in zip(nim_wrapper_fnames, pymodule_fnames)
            ] + [
            "%s: %s\n\t%s $(PMGEN) %s" %
                    # FIXME: This is not necessarily correct.
                    # The `pminc_fname` for THIS invocation is not necessarily
                    # the `pminc_fname` that was used to generate this
                    # "pmgen*_wrap.nim" file in a previous invocation of
                    # "pmgen.py".
                    (nim_fname, pminc_fname, NIM_COMPILER_COMMAND % "compile", pminc_fname)
                    for nim_fname in nim_wrapper_fnames
            ] + [
            "%s: %s\n\tcd .. ; %s %s %s" %
                    (pminc_fname, " ".join(nim_modfiles_rel_pmgen_dir),
                            python_exe_name,
                            abspath_to_pmgen_py, " ".join(nim_modfiles))
            ]

    makefile_fname = MAKEFILE2_FNAME_TEMPLATE
    makefile_clean_rules = MAKEFILE_CLEAN_RULES % dict(
            pmgen_prefix=PMGEN_PREFIX)
    with open(makefile_fname, "w") as f:
        f.write(MAKEFILE_CONTENT % dict(
                datestamp=datestamp,
                variables=MAKEFILE_PMGEN_VARIABLE % define_python3_maybe(),
                build_rules="\n\n".join(build_rules),
                clean_rules=makefile_clean_rules))

    make_command = [MAKE_EXE_PATH, "-f", makefile_fname]
    print(" ".join(make_command))
    subprocess.check_call(make_command)


def define_python3_maybe():
    python_ver = sys.version_info
    if python_ver.major >= 3:
        return "--define:python3"
    else:
        return ""


def test_that_numpy_is_installed():
    try:
        import numpy
    except ImportError as e:
        die("unable to import Python module `numpy`")

    numpy_inst_path = numpy.__file__
    if not os.path.isdir(numpy_inst_path):
        numpy_inst_path = os.path.dirname(numpy_inst_path)
    print("Found Numpy installation at: %s" % numpy_inst_path)

    numpy_paths = numpy.__path__
    print("Numpy installation paths: %s" % numpy_paths)
    return numpy_paths


def determine_python_includes_ldflags():
    # The most likely-to-be-correct way:  Use the script "python-config" that
    # comes with the Python installation.
    (includes, ldflags, python_config_exe_name) = \
            determine_python_includes_ldflags_use_python_config()
    if includes is not None and ldflags is not None:
        # Success!
        print("Determined Python C-API includes & ldflags using command `%s`" % python_config_exe_name)
        print(" - includes = %s" % includes)
        print(" - ldflags = %s" % ldflags)
        return (includes, ldflags)

    # Otherwise, fall back on Plan B:  Guess what we can, using variables in
    # the `sysconfig` module.
    #  https://docs.python.org/2/library/sysconfig.html
    #  https://docs.python.org/3/library/sysconfig.html
    (includes, ldflags) = guess_python_includes_ldflags_use_sysconfig()
    if includes is not None and ldflags is not None:
        # Success!
        print("Determined Python C-API includes & ldflags using Python `sysconfig` module")
        print(" - includes = %s" % includes)
        print(" - ldflags = %s" % ldflags)
        return (includes, ldflags)

    # Otherwise, Plan C:  Assume we're on an unusually-undemanding UNIX system,
    # and make some optimistic guesses based upon info in the `sys` module.
    #  https://docs.python.org/2/library/sys.html#sys.platform
    #  https://docs.python.org/2/library/sys.html#sys.prefix
    #  https://docs.python.org/2/library/sys.html#sys.version_info
    #  https://docs.python.org/3/library/sys.html
    python_ver = sys.version_info
    python_header_comp = "python%d.%d" % (python_ver.major, python_ver.minor)
    python_header_path = os.path.join(sys.prefix, "include", python_header_comp)
    includes = ["-I" + python_header_path]

    python_lib_name = "python%d.%d" % (python_ver.major, python_ver.minor)
    ldflags = ["-l" + python_lib_name]

    print("Last resort: Guessed Python C-API includes & ldflags using Python `sys` module")
    print(" - includes = %s" % includes)
    print(" - ldflags = %s" % ldflags)
    return (includes, ldflags)


def determine_python_includes_ldflags_use_python_config():
    # https://docs.python.org/2/library/sys.html#sys.executable
    python_exe_path = sys.executable
    if not python_exe_path:
        # "If Python is unable to retrieve the real path to its executable,
        # `sys.executable` will be an empty string or None."
        return (None, None, None)

    python_exe_name = os.path.split(python_exe_path)[-1]
    python_config_exe_name = "%s-config" % python_exe_name
    try:
        includes = subprocess.check_output([python_config_exe_name, "--includes"])
        #libs = subprocess.check_output([python_config_exe_name, "--libs"])
        #cflags = subprocess.check_output([python_config_exe_name, "--cflags"])
        ldflags = subprocess.check_output([python_config_exe_name, "--ldflags"])
    except OSError as e:
        print("Caught OSError(%s)" % str(e), file=sys.stderr)
        return (None, None, python_config_exe_name)

    python_ver = sys.version_info
    if python_ver.major >= 3:
        # Stupid byte/string dichotomy...
        includes = includes.decode(encoding='UTF-8')
        ldflags = ldflags.decode(encoding='UTF-8')

    includes = includes.split()
    ldflags = ldflags.split()

    return (includes, ldflags, python_config_exe_name)


def guess_python_includes_ldflags_use_sysconfig():
    import sysconfig

    # The following code is copied from
    # "/usr/lib/python3.4/config-3.4m-x86_64-linux-gnu/python-config.py"
    # on my system.
    getpath = sysconfig.get_path
    getvar = sysconfig.get_config_var
    pyver = getvar('VERSION')

    includes = ["-I"+p for p in [getpath("include"), getpath("platinclude")]]

    libpython = "-lpython" + pyver
    if hasattr(sys, "abiflags"):
        libpython += sys.abiflags
    ldflags = [libpython]
    ldflags += getvar('LIBS').split()
    ldflags += getvar('SYSLIBS').split()
    # Add the "prefix/lib/pythonX.Y/config" dir, but only if there is
    # no shared library in "prefix/lib/".
    if not getvar('Py_ENABLE_SHARED'):
        ldflags.insert(0, '-L' + getvar('LIBPL'))
    if not getvar('PYTHONFRAMEWORK'):
        ldflags.extend(getvar('LINKFORSHARED').split())

    return (includes, ldflags)


def die(msg):
    print("%s: %s\nAborted." % (sys.argv[0], msg), file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

