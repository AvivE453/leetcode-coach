from dataclasses import dataclass
from datetime import date, timedelta

QUALITY = {"clean": 5, "struggled": 3, "hints": 2, "failed": 1}
INITIAL_EASE = 2.5
MIN_EASE = 1.3
SECOND_INTERVAL = 6.0


@dataclass(frozen=True)
class ReviewState:
    ease: float
    interval_days: float
    next_due: date
    reps: int
    lapses: int


def review(state: ReviewState | None, outcome: str, today: date) -> ReviewState:
    quality = QUALITY[outcome]
    ease = state.ease if state else INITIAL_EASE
    reps = state.reps if state else 0
    lapses = state.lapses if state else 0

    ease = max(MIN_EASE, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))

    if quality < 3:
        reps = 0
        lapses += 1
        interval = 1.0
    else:
        reps += 1
        if reps == 1:
            interval = 1.0
        elif reps == 2:
            interval = SECOND_INTERVAL
        else:
            interval = state.interval_days * ease

    return ReviewState(
        ease=ease,
        interval_days=interval,
        next_due=today + timedelta(days=round(interval)),
        reps=reps,
        lapses=lapses,
    )
