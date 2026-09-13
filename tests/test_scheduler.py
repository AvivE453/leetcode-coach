from datetime import date, timedelta

import pytest

from coach import scheduler

TODAY = date(2026, 8, 31)

CLEAN, STRUGGLED, HINTS, FAILED = (
    scheduler.QUALITY[outcome] for outcome in ("clean", "struggled", "hints", "failed")
)


def test_first_clean_review_due_in_a_week():
    s = scheduler.review(None, CLEAN, TODAY)
    assert s.reps == 1
    assert s.interval_days == scheduler.FIRST_INTERVAL
    assert s.next_due == TODAY + timedelta(days=7)
    assert s.ease > scheduler.INITIAL_EASE


def test_clean_progression_stretches_intervals():
    s = scheduler.review(None, CLEAN, TODAY)
    s = scheduler.review(s, CLEAN, TODAY + timedelta(days=7))
    assert s.interval_days == scheduler.SECOND_INTERVAL

    s2 = scheduler.review(s, CLEAN, TODAY + timedelta(days=21))
    assert s2.interval_days == pytest.approx(s.interval_days * s2.ease)
    assert s2.interval_days > 30


def test_struggled_advances_but_lowers_ease():
    s = scheduler.review(None, CLEAN, TODAY)
    ease_before = s.ease
    s = scheduler.review(s, STRUGGLED, TODAY + timedelta(days=7))
    assert s.reps == 2
    assert s.interval_days == scheduler.SECOND_INTERVAL
    assert s.ease < ease_before


def test_failed_resets_to_the_lapse_interval():
    s = scheduler.review(None, CLEAN, TODAY)
    s = scheduler.review(s, CLEAN, TODAY + timedelta(days=7))
    s = scheduler.review(s, FAILED, TODAY + timedelta(days=21))
    assert s.reps == 0
    assert s.lapses == 1
    assert s.interval_days == scheduler.LAPSE_INTERVAL
    assert s.next_due == TODAY + timedelta(days=24)


def test_hints_also_resets():
    s = scheduler.review(None, HINTS, TODAY)
    assert s.reps == 0
    assert s.lapses == 1
    assert s.interval_days == scheduler.LAPSE_INTERVAL


def test_intervals_stop_growing_at_the_cap():
    s = None
    day = TODAY
    for _ in range(10):
        s = scheduler.review(s, CLEAN, day)
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
    s = scheduler.review(capped, CLEAN, TODAY)
    assert s.interval_days == scheduler.MAX_INTERVAL
    assert s.next_due == TODAY + timedelta(days=180)


def test_ease_never_drops_below_floor():
    s = None
    day = TODAY
    for _ in range(10):
        s = scheduler.review(s, FAILED, day)
        day += timedelta(days=1)
    assert s.ease == pytest.approx(scheduler.MIN_EASE)


def test_same_day_attempts_count_as_one_review():
    """Logging a problem again in the same sitting proves nothing about remembering it a
    week out, so three clean logs in a day schedule like one: 7 days, not 7, 14, then 39."""
    s = scheduler.replay([(TODAY, CLEAN)] * 3)

    assert s == scheduler.review(None, CLEAN, TODAY)
    assert s.next_due == TODAY + timedelta(days=7)


@pytest.mark.parametrize("first, second", [(FAILED, CLEAN), (CLEAN, FAILED)])
def test_a_day_is_graded_by_its_worst_attempt(first, second):
    """A clean retry after reading the solution does not undo the failure before it, and a
    failed retry still undoes the clean solve before it: either way the day is a lapse."""
    review_day = TODAY + timedelta(days=7)

    s = scheduler.replay([(TODAY, CLEAN), (review_day, first), (review_day, second)])

    assert (s.reps, s.lapses) == (0, 1)
    assert s.interval_days == scheduler.LAPSE_INTERVAL
    assert s.next_due == review_day + timedelta(days=3)


def test_a_day_holding_a_grade_capped_below_three_is_a_lapse():
    """A clean solve whose review reported an edge case grades 2 - under the lapse line
    that struggled's 3 sits on - so a clean retry beside it still lapses the problem."""
    s = scheduler.replay([(TODAY, CLEAN), (TODAY, 2)])

    assert (s.reps, s.lapses) == (0, 1)
    assert s.next_due == TODAY + timedelta(days=3)


def test_failing_repeatedly_in_one_day_lapses_once():
    """The mirror of the same-day stretch: three failed tries in one sitting would stack
    three lapses and floor the ease, shortening every interval the problem has after."""
    s = scheduler.replay([(TODAY, FAILED)] * 3)

    assert s == scheduler.review(None, FAILED, TODAY)
    assert s.lapses == 1
    assert s.ease > scheduler.MIN_EASE


def test_attempts_on_different_days_are_separate_reviews():
    """Days that land on their due dates replay exactly as the step-by-step fold: the
    7 -> 14 -> x ease ladder is untouched by the same-day and early-success rules."""
    days = [TODAY, TODAY + timedelta(days=7), TODAY + timedelta(days=21)]
    by_hand = None
    for day in days:
        by_hand = scheduler.review(by_hand, CLEAN, day)

    s = scheduler.replay([(day, CLEAN) for day in days])

    assert s == by_hand
    assert s.interval_days > scheduler.SECOND_INTERVAL


def test_clean_solves_on_consecutive_days_schedule_like_one():
    """The same-day stretch spread over a few days: solving again the next morning shows no
    more remembering than solving again that afternoon, so it is still 7 days, not 39."""
    days = [TODAY + timedelta(days=offset) for offset in range(3)]

    s = scheduler.replay([(day, CLEAN) for day in days])

    assert s == scheduler.review(None, CLEAN, TODAY)
    assert s.next_due == TODAY + timedelta(days=7)


@pytest.mark.parametrize("quality", [CLEAN, STRUGGLED])
def test_a_success_before_the_review_is_due_changes_nothing(quality):
    """Approach practice brings a problem back after three days, four before its review:
    solving it then neither stretches the interval nor touches the ease."""
    s = scheduler.replay([(TODAY, CLEAN), (TODAY + timedelta(days=3), quality)])

    assert s == scheduler.review(None, CLEAN, TODAY)


@pytest.mark.parametrize("quality", [HINTS, FAILED])
def test_a_failure_before_the_review_is_due_still_lapses(quality):
    """Forgetting is evidence whenever it shows, so an early failure resets the problem."""
    failed_on = TODAY + timedelta(days=2)

    s = scheduler.replay([(TODAY, CLEAN), (failed_on, quality)])

    assert (s.reps, s.lapses) == (0, 1)
    assert s.next_due == failed_on + timedelta(days=3)


@pytest.mark.parametrize("offset, reps, due_offset", [(6, 1, 7), (7, 2, 21), (10, 2, 24)])
def test_a_passing_day_counts_from_its_due_date(offset, reps, due_offset):
    """The day before the review is still early; the due date itself and any later day count."""
    s = scheduler.replay([(TODAY, CLEAN), (TODAY + timedelta(days=offset), CLEAN)])

    assert (s.reps, s.next_due) == (reps, TODAY + timedelta(days=due_offset))


def test_after_a_lapse_a_success_waits_for_the_lapse_interval():
    """A clean retry the next day, after reading the solution, is not the problem remembered:
    the lapse still brings it back on the third day, and only that solve restarts the ladder."""
    retries = [(TODAY, FAILED), (TODAY + timedelta(days=1), CLEAN), (TODAY + timedelta(days=2), CLEAN)]

    lapsed = scheduler.replay(retries)
    relearned = scheduler.replay([*retries, (TODAY + timedelta(days=3), CLEAN)])

    assert lapsed == scheduler.review(None, FAILED, TODAY)
    assert (relearned.reps, relearned.next_due) == (1, TODAY + timedelta(days=10))


SOLVED_TODAY = scheduler.review(None, CLEAN, TODAY)  # due in a week


@pytest.mark.parametrize(
    "state, quality, day, counts",
    [
        (None, CLEAN, TODAY, True),  # the first day
        (SOLVED_TODAY, FAILED, TODAY + timedelta(days=1), True),  # a failure, however early
        (SOLVED_TODAY, STRUGGLED, TODAY + timedelta(days=1), False),  # a success before the due date
        (SOLVED_TODAY, CLEAN, TODAY + timedelta(days=7), True),  # on the due date
        (SOLVED_TODAY, CLEAN, TODAY + timedelta(days=30), True),  # overdue
    ],
)
def test_counts_as_review(state, quality, day, counts):
    assert scheduler.counts_as_review(state, quality, day) is counts
