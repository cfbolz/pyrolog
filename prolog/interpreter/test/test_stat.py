from prolog.interpreter.stat import LRUHistogram

def test_hist():
    h = LRUHistogram()
    h.see(1)
    h.see(1)
    assert h.get_usage(1) == 2
    for i in range(2, 6):
        h.see(i)
        assert h.get_usage(i) == 1
    assert h.usage == [4, 3, 2, 1, 0]
