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


def test_same_day_attempts_count_as_one_review():
    """Logging a problem again in the same sitting proves nothing about remembering it a
    week out, so three clean logs in a day schedule like one: 7 days, not 7, 14, then 39."""
    s = scheduler.replay([(TODAY, "clean")] * 3)

    assert s == scheduler.review(None, "clean", TODAY)
    assert s.next_due == TODAY + timedelta(days=7)


@pytest.mark.parametrize("first, second", [("failed", "clean"), ("clean", "failed")])
def test_a_day_is_graded_by_its_worst_attempt(first, second):
    """A clean retry after reading the solution does not undo the failure before it, and a
    failed retry still undoes the clean solve before it: either way the day is a lapse."""
    review_day = TODAY + timedelta(days=7)

    s = scheduler.replay([(TODAY, "clean"), (review_day, first), (review_day, second)])

    assert (s.reps, s.lapses) == (0, 1)
    assert s.interval_days == scheduler.LAPSE_INTERVAL
    assert s.next_due == review_day + timedelta(days=3)


def test_failing_repeatedly_in_one_day_lapses_once():
    """The mirror of the same-day stretch: three failed tries in one sitting would stack
    three lapses and floor the ease, shortening every interval the problem has after."""
    s = scheduler.replay([(TODAY, "failed")] * 3)

    assert s == scheduler.review(None, "failed", TODAY)
    assert s.lapses == 1
    assert s.ease > scheduler.MIN_EASE


def test_attempts_on_different_days_are_separate_reviews():
    """Across days, replaying is exactly the step-by-step fold: the 7 -> 14 -> x ease
    ladder is untouched by the same-day rule."""
    days = [TODAY, TODAY + timedelta(days=7), TODAY + timedelta(days=21)]
    by_hand = None
    for day in days:
        by_hand = scheduler.review(by_hand, "clean", day)

    s = scheduler.replay([(day, "clean") for day in days])

    assert s == by_hand
    assert s.interval_days > scheduler.SECOND_INTERVAL
