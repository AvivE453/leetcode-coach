from datetime import date, timedelta

import pytest

from coach import scheduler

TODAY = date(2026, 8, 31)


def test_first_clean_review_due_tomorrow():
    s = scheduler.review(None, "clean", TODAY)
    assert s.reps == 1
    assert s.interval_days == 1.0
    assert s.next_due == TODAY + timedelta(days=1)
    assert s.ease > scheduler.INITIAL_EASE


def test_clean_progression_stretches_intervals():
    s = scheduler.review(None, "clean", TODAY)
    s = scheduler.review(s, "clean", TODAY + timedelta(days=1))
    assert s.interval_days == scheduler.SECOND_INTERVAL

    s2 = scheduler.review(s, "clean", TODAY + timedelta(days=7))
    assert s2.interval_days == pytest.approx(s.interval_days * s2.ease)
    assert s2.interval_days > 15


def test_struggled_advances_but_lowers_ease():
    s = scheduler.review(None, "clean", TODAY)
    ease_before = s.ease
    s = scheduler.review(s, "struggled", TODAY + timedelta(days=1))
    assert s.reps == 2
    assert s.interval_days == scheduler.SECOND_INTERVAL
    assert s.ease < ease_before


def test_failed_resets_to_one_day():
    s = scheduler.review(None, "clean", TODAY)
    s = scheduler.review(s, "clean", TODAY + timedelta(days=1))
    s = scheduler.review(s, "failed", TODAY + timedelta(days=7))
    assert s.reps == 0
    assert s.lapses == 1
    assert s.interval_days == 1.0
    assert s.next_due == TODAY + timedelta(days=8)


def test_hints_also_resets():
    s = scheduler.review(None, "hints", TODAY)
    assert s.reps == 0
    assert s.lapses == 1
    assert s.interval_days == 1.0


def test_ease_never_drops_below_floor():
    s = None
    day = TODAY
    for _ in range(10):
        s = scheduler.review(s, "failed", day)
        day += timedelta(days=1)
    assert s.ease == pytest.approx(scheduler.MIN_EASE)
