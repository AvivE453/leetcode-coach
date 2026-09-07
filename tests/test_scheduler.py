from datetime import date, timedelta

import pytest

from coach import scheduler

TODAY = date(2026, 8, 31)


def test_first_clean_review_due_in_a_week():
    s = scheduler.review(None, "clean", TODAY)
    assert s.reps == 1
    assert s.interval_days == scheduler.FIRST_INTERVAL
    assert s.next_due == TODAY + timedelta(days=7)
    assert s.ease > scheduler.INITIAL_EASE


def test_clean_progression_stretches_intervals():
    s = scheduler.review(None, "clean", TODAY)
    s = scheduler.review(s, "clean", TODAY + timedelta(days=7))
    assert s.interval_days == scheduler.SECOND_INTERVAL

    s2 = scheduler.review(s, "clean", TODAY + timedelta(days=21))
    assert s2.interval_days == pytest.approx(s.interval_days * s2.ease)
    assert s2.interval_days > 30


def test_struggled_advances_but_lowers_ease():
    s = scheduler.review(None, "clean", TODAY)
    ease_before = s.ease
    s = scheduler.review(s, "struggled", TODAY + timedelta(days=7))
    assert s.reps == 2
    assert s.interval_days == scheduler.SECOND_INTERVAL
    assert s.ease < ease_before


def test_failed_resets_to_the_lapse_interval():
    s = scheduler.review(None, "clean", TODAY)
    s = scheduler.review(s, "clean", TODAY + timedelta(days=7))
    s = scheduler.review(s, "failed", TODAY + timedelta(days=21))
    assert s.reps == 0
    assert s.lapses == 1
    assert s.interval_days == scheduler.LAPSE_INTERVAL
    assert s.next_due == TODAY + timedelta(days=24)


def test_hints_also_resets():
    s = scheduler.review(None, "hints", TODAY)
    assert s.reps == 0
    assert s.lapses == 1
    assert s.interval_days == scheduler.LAPSE_INTERVAL


def test_intervals_stop_growing_at_the_cap():
    s = None
    day = TODAY
    for _ in range(10):
        s = scheduler.review(s, "clean", day)
        day += timedelta(days=round(s.interval_days))
    assert s.interval_days == scheduler.MAX_INTERVAL


def test_a_capped_interval_stays_capped():
    """The stored interval is clamped too, so the next review multiplies 180 -
    not an ever-growing number - and lands back on 180."""
    capped = scheduler.ReviewState(
        ease=3.0,
        interval_days=scheduler.MAX_INTERVAL,
        next_due=TODAY,
        reps=8,
        lapses=0,
    )
    s = scheduler.review(capped, "clean", TODAY)
    assert s.interval_days == scheduler.MAX_INTERVAL
    assert s.next_due == TODAY + timedelta(days=180)


def test_ease_never_drops_below_floor():
    s = None
    day = TODAY
    for _ in range(10):
        s = scheduler.review(s, "failed", day)
        day += timedelta(days=1)
    assert s.ease == pytest.approx(scheduler.MIN_EASE)
