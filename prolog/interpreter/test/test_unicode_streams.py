# coding: utf-8
import os
import pytest
from rpython.rlib.streamio import fdopen_as_stream
from prolog.interpreter.stream import PrologInputStream
from prolog.builtin.streams import read_unicode_char, peek_unicode_char
from prolog.interpreter.test.tool import assert_true, prolog_raises


def test_utf8_file_roundtrip(tmpdir):
    path = str(tmpdir.join('unicode.txt'))
    assert_true("open('%s',write,S,[encoding(utf8)]), "
                "put_char(S,'é'), put_code(S,8364), put_code(S,128512), "
                "put_code(S,0), close(S)." % path)
    assert open(path, 'rb').read() == 'é€😀\x00'
    assert_true("open('%s',read,S), peek_code(S,233), peek_char(S,'é'), "
                "get_code(S,233), get_char(S,'€'), peek_code(S,128512), "
                "get_code(S,128512), get_code(S,0), peek_code(S,-1), "
                "get_char(S,end_of_file), close(S)." % path)


def test_utf8_pipe_peeking():
    readfd, writefd = os.pipe()
    os.write(writefd, 'é€😀')
    os.close(writefd)
    stream = PrologInputStream(fdopen_as_stream(readfd, 'r'))
    try:
        for char in ['é', '€', '😀']:
            assert peek_unicode_char(stream) == char
            assert peek_unicode_char(stream) == char
            assert read_unicode_char(stream) == (char, len(char))
        assert peek_unicode_char(stream) == 'end_of_file'
    finally:
        stream.close()


@pytest.mark.parametrize('data', ['\xff', '\xc0\x80', '\xed\xa0\x80', '\xf4\x90\x80\x80', '\xe2\x82', '\xe2A'])
def test_invalid_utf8_stream(tmpdir, data):
    path = tmpdir.join('bad.txt')
    path.write(data, mode='wb')
    prolog_raises('representation_error(character)',
                  "open('%s',read,S), get_code(S,_)" % path)


def test_binary_bytes_and_stream_types(tmpdir):
    path = str(tmpdir.join('bytes'))
    assert_true("open('%s',write,S,[type(binary)]), put_byte(S,0), "
                "put_byte(S,255), close(S), open('%s',read,R,[type(binary)]), "
                "peek_byte(R,0), get_byte(R,0), get_byte(R,255), "
                "get_byte(R,-1), close(R)." % (path, path))
    prolog_raises('permission_error(input,binary_stream,_)',
                  "open('%s',read,S,[type(binary)]),get_char(S,_)" % path)
    prolog_raises('permission_error(input,text_stream,_)',
                  "open('%s',read,S),get_byte(S,_)" % path)
    prolog_raises('permission_error(output,binary_stream,_)',
                  "open('%s',write,S,[type(binary)]),put_code(S,233)" % path)
    prolog_raises('type_error(byte,256)',
                  "open('%s',write,S,[type(binary)]),put_byte(S,256)" % path)


@pytest.mark.parametrize('goal', ['open(P,read,_)', 'consult(P)', 'see(P)', 'add_library_dir(P)'])
def test_nul_is_valid_in_atoms_but_not_os_paths(goal):
    prolog_raises('domain_error(source_sink,_)',
                  'atom_codes(P,[97,0,98]), ' + goal)


def test_consult_unicode_filename_and_bom(tmpdir):
    path = str(tmpdir) + '/词.pl'
    with open(path, 'wb') as f:
        f.write('\xef\xbb\xbf词(😀).\n')
    assert_true("consult('%s'), 词('😀')." % path)
