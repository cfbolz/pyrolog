import pytest
import time
from prolog.interpreter.continuation import Engine
from prolog.interpreter.test.tool import assert_true


def test_statistics():
    assert_true("statistics(runtime, X).", Engine())


def test_statistics_builds_list():
    assert_true('statistics(runtime, [A,B]), number(A), number(B).', Engine())


@pytest.mark.parametrize('stat, clock', [
    ('runtime', 'clock'), ('walltime', 'time'),
])
def test_statistics_elapsed_milliseconds(monkeypatch, stat, clock):
    engine = Engine()
    now = [100.0]
    monkeypatch.setattr(time, clock, lambda: now[0])
    engine.clocks.startup()

    # A first query in the same millisecond legitimately returns zero.
    assert_true('statistics(%s, [0, 0]).' % stat, engine)
    now[0] += 0.125
    assert_true('statistics(%s, [125, 125]).' % stat, engine)
    now[0] += 0.5
    assert_true('statistics(%s, [625, 500]).' % stat, engine)
    assert_true('statistics(%s, [625, 0]).' % stat, engine)

    # Startup resets both total and time-since-last-call accounting.
    engine.clocks.startup()
    now[0] += 0.25
    assert_true('statistics(%s, [250, 250]).' % stat, engine)


@pytest.mark.parametrize('stat, clock', [
    ('runtime', 'clock'), ('walltime', 'time'),
])
def test_statistics_first_call_reports_total(monkeypatch, stat, clock):
    engine = Engine()
    now = [100.0]
    monkeypatch.setattr(time, clock, lambda: now[0])
    engine.clocks.startup()
    now[0] += 2.0
    assert_true('statistics(%s, [2000, 2000]).' % stat, engine)
