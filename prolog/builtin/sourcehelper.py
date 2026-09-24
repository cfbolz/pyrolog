import os
import sys
from prolog.interpreter.error import throw_existence_error, throw_domain_error
from prolog.interpreter.term import Callable
from rpython.rlib import rstring

path = os.path.dirname(__file__)
path = os.path.join(path, "..", "prolog_modules")

def get_source(filename):
    try:
        assert isinstance(filename, str)
        fd, actual_filename = get_filehandle(filename, True)
    except OSError:
        throw_existence_error("source_sink", Callable.build(filename))
        assert 0, "unreachable" # make the flow space happy
    try:
        content = []
        while 1:
            s = os.read(fd, 4096)
            if not s:
                break
            content.append(s)
        file_content = "".join(content)
    finally:
        os.close(fd)
    return file_content, actual_filename

def path_for_os(filename):
    if '\x00' in filename:
        throw_domain_error('source_sink', Callable.build(filename))
    return rstring.assert_str0(filename)


def get_filehandle(filename, stdlib=False):
    filename = path_for_os(filename)
    filename_with_pl =  filename + '.pl'
    candidates = [
        filename,
        filename_with_pl,
        os.path.join(path, filename),
        os.path.join(path, filename_with_pl)]
    e = None
    for cand in candidates:
        try:
            return os.open(cand, os.O_RDONLY, 0777), os.path.abspath(cand)
        except OSError, e:
            pass
    assert e is not None
    raise e
