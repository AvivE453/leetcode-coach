# Logic

How the coach turns the practice history ([history.md](history.md)) into grades, a review
schedule, mastery per pattern, approach practice, the Daily Plan and the Weekly Review. All of it
is computed from the history on every read; the review schedule is the one result that is
stored.

## Grading an attempt

Every attempt gets one grade from 1 to 5, in [coach/assessment.py](../coach/assessment.py), and
both the review schedule and mastery use that same grade, so they cannot disagree about what an
attempt showed. Before this, mastery blended a review in while the schedule ignored it: a clean
solve whose review reported a bug scored low for its pattern and was still scheduled as a perfect
recall.

The grade starts from the outcome logged with the solve:

| Outcome | Grade |
|---|---|
| `clean` | 5 |
| `struggled` | 3 |
| `hints` | 2 |
| `failed` | 1 |

A review can only lower it. It is a model's judgement, not an executed test, so a reported
problem caps the grade, but an "optimal" review never turns a solve that needed hints into
evidence of mastery:

| What the review reports | Highest grade |
|---|---|
| A bug (wrong on an ordinary input) | 1 |
| An edge case (wrong only at a boundary) | 2 |
| A `needs-work` verdict naming neither | 2 |
| Only complexity remarks, or nothing | no cap |

The ceilings are a policy, not a calibrated prediction of how well the problem is remembered.
The issue categories outrank the verdict, because they name the failing input: an `optimal`
verdict that lists a bug is a bug. Complexity remarks describe correct code, so they are no
correctness finding; mastery weighs the review's verdict separately.

A review saved days after the solve re-grades that attempt, and the problem's schedule is
replayed in the same transaction. It is never added as a new event on the day it arrives:
re-running a review would count the same evidence twice, and the schedule would depend on when
the button was clicked.

**Why a problem came back.** `assessment.findings` gives each problem's worst finding on the
last day it was practiced, which the Daily Plan shows as the reason ("re-solve: review reported a
bug"). The last day rather than the last attempt, because the schedule grades a day by its worst
attempt: a clean retry minutes after a bug was found leaves the problem lapsed, so it does not
clear the reason either. Practice on a later day moves past it.

## The review schedule

Each attempted problem has a spaced-repetition schedule, in
[coach/scheduler.py](../coach/scheduler.py): when to solve it again so it is tested just before
it would be forgotten. It follows SM-2, the SuperMemo 2 algorithm. Each problem has an *ease*
(starting at 2.5, never below 1.3) that every counted review nudges by the grade, and an
interval that grows by the ease after each success:

```python
ease = max(1.3, ease + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
```

A grade of 5 adds 0.1 to the ease, 4 leaves it, 3 takes 0.14 off. The intervals are this
project's numbers rather than SM-2's (1 and 6 days): 7 days after the first success, 14 after
the second, then the previous interval times the ease, capped at 180 days. A grade below 3 is a
lapse: the success count resets and the problem comes back in 3 days. Three clean days on their
due dates go 7, 14, then 39 days (14 × 2.8).

### A day is one review, and an early success is none

The schedule is not stepped once per logged solve. `scheduler.replay` rebuilds it from all of a
problem's attempts each time:

- **Attempts on the same day are one review, graded by the worst of them.** Solving a problem
  again in the same sitting, after reading the solution or just once more, shows nothing about
  remembering it weeks later. A failure grades its day whichever order it came in, and three
  failed tries lapse the problem once instead of flooring its ease.
- **A passing day before the problem is due is no review** (`counts_as_review`): it changes
  nothing, not even the ease. Solving early shows nothing about remembering at the interval the
  schedule would stretch to. A failing day always counts, however early: forgetting is evidence
  whenever it shows.
- **One exception, for solves the plan asked for.** Whether a problem was due is a fact of the
  moment it was logged, and a review re-run later can change what the replay thinks that moment
  was. So `log_solve` records it (`solutions.due_when_logged`), and a passing day logged while due
  that the replay finds early restarts the clock at the interval it has, without stretching it.

Because the schedule is a replay, its rules have one owner, and `coach init` re-derives every
stored schedule (`service.rebuild_review_states`) when they change.

### What is due

`scheduler.due_reviews` is the one query for which reviews are owed: `next_due` on or before
today plus a horizon (`lookahead_days`), soonest first. The Daily Plan and Home's "Due for
review" card both ask it with a horizon of 0. Dates are stored as ISO text (`2026-10-25`), which
sorts in date order, so SQLite, which has no date type, compares them as strings.

## Mastery per pattern

Each pattern a solve led with gets one mastery score from 1 to 5, in
[coach/mastery.py](../coach/mastery.py). It answers "how is this pattern going" across every
problem that used it, where the review schedule answers "when should I see this problem again".

**One solve's score.** Without a review, it is the solve's grade. With one, it blends how the
solve felt with what the review found, and is capped by the grade:

```python
min(0.5 * outcome + 0.5 * review, grade)
```

The review part is the verdict (`optimal` 5, `acceptable` 4), or the correctness ceiling when it
reports a bug or an edge case, and more findings can only pull it down (2 findings cap it at 3,
3-4 at 2, 5 or more at 1). Without the cap, a clean solve with a reported bug scored 3.8, so no
number of them could make a pattern weak, and an optimal review lifted a solve that needed hints
to 2.9 (both under the earlier 0.7/0.3 blend).

**Folding the solves.** A pattern's solves, oldest first, fold through an exponential moving
average with α = 0.25: each new solve moves the score a quarter of the way toward its own, so recent
solves count most and old ones fade without being thrown away. The first solve seeds the score
as it is, rather than starting from an invented middle value. A solve with several main patterns
counts in full for each; secondary patterns and untagged solves count for none.

**Weak** means a score below 3 across at least 3 distinct problems. The floor counts problems,
not attempts, because SM-2 brings a failed problem back every three days, so one hard problem
could pile up attempts on its own; that says something about the problem, which the schedule
already handles, not about the pattern. `mastery.is_weak` holds the rule, and `analyze()` is the
only thing that produces the list of weak patterns.

Nothing is stored: every read folds the whole history again, so a review that arrives days
after its solve counts the moment it is saved. Measured on synthetic histories, the Weekly
Review's read takes 0.2 ms at today's size, 7 ms at a year of 25 solves a week, and 83 ms at
ten years.

## Approach practice

A solve can be correct and still miss what the problem teaches: a two-loop brute force on a
sliding-window problem is a clean solve to SM-2. Approach practice brings such a problem back
until it has been solved the intended way, in [coach/corrections.py](../coach/corrections.py).
It is three questions, kept apart:

- **Off-pattern**: a solve whose main and secondary tags name none of the problem's accepted
  approaches (`enrich.off_pattern`, a set intersection). A problem never enriched has no
  accepted set, so nothing on it is ever off-pattern.
- **Owed**: some attempt was off-pattern and no attempt **qualifies**. An attempt qualifies
  when its own tags hit the accepted set on a day with no grade below 3, the line SM-2 lapses a
  day on. So a solve that failed, needed hints, or has a review reporting a bug, an edge case
  or needs-work completes nothing, and neither does a clean retry typed in right after one of
  those on the same day. The tags and the success must belong to one attempt: a failed DP solve
  beside a clean brute force is not "solved with DP".
- **Due**: three days after the latest attempt of any kind, so practising a problem, however
  it went, never brings it back the next day.

One qualifying attempt closes it for good: brute-forcing the problem again later is an
experiment, and forgetting the approach is SM-2's job. An untagged solve is neither evidence
nor success until `coach enrich` tags it, but it still moves the date, because it was practice.
Completing approach practice never advances the review: a success before the review is due
leaves its date alone, so the two can come due on different days.

Nothing is stored. `owed()` judges every problem over `history.load()`'s attempts on each read,
so a review saved later, a backfilled tag or a widened accepted set counts on the next page
load. A problem reopened that way is due three days after the practice being judged, usually
already past, not three days after the evidence arrived. The log page learns that a solve
completed approach practice the same way: `service.practice_dates` judges the history with
and without that solve, and the practice is completed when it was owed before and not after.

## The Daily Plan

The Daily Plan answers "what do I solve today", recomputed on every page load and stored
nowhere: a solved problem simply stops appearing. `service.daily_plan` runs `analyze()` with
`lookahead_days=0`, then [coach/weekly/plan.py](../coach/weekly/plan.py)'s `build_plan` fills
three headings of at most `SECTION_LIMIT` (10) problems each, owed work first:

1. **Due**: the reviews due today or overdue, most overdue first, each worded by a review's
   reported failure when its last practice day has one. A problem that also owes approach
   practice stays here, as one item carrying both reasons.
2. **Approach practice**: the approach practice due, minus problems already under Due.
3. **Weak patterns**: unsolved problems from the curriculum (`config.CURRICULUM`, NeetCode 150,
   which contains all of Blind 75) carrying a weak pattern's official LeetCode tag, weakest
   pattern first, at most 3 per pattern so the weakest cannot take every slot. When a pattern's
   curriculum problems have all been attempted, it gets no picks.
4. **Curriculum progression** tops Due up to ten when fewer reviews are due, in the
   curriculum's own order. It runs last, so it never takes a problem a weak pattern would have
   picked.

The headings have separate budgets because one shared list did not work: it used to be fifteen
ranked slots, and a heavy review day pushed approach practice and weak picks off the page with
nothing saying so. Approach practice comes before weak picks because it is owed on a problem
already solved the wrong way, while a weak pick is a new, optional problem. For the same reason
only new picks meet the Hard cap, one in five per heading (`hard_cap`), counting a Hard review
already under that heading.

One set of claimed numbers keeps any problem from appearing twice, and Due claims every review
due, listed or not. A review that does not fit stays overdue and comes first tomorrow, and the
heading says how many it left out, instead of turning up under Approach practice without its
review. The horizon is today because a success before a review is due does not count as the
review: a review due on Friday listed today would take a slot and move nothing.

Our pattern tags diagnose a weakness, and the official tags pick the problems to fix it
(`PATTERN_TO_TAG`): a problem not yet attempted has no tags of ours. A pattern with no matching
official tag, like `intervals`, gets no weak picks. Each item carries its reasons as a `kind`
(review, re-solve, weak-pattern, curriculum) set where the rule fires, which the page also uses
to style the reason, plus the sentence shown.

## The Weekly Review

The Weekly Review looks back over the last seven days, today included
(`weekly/collect.py`, `window`), and answers two questions: what was solved, and whether the
week moved each pattern it used. `service.weekly_review` loads the history once and hands the
same attempts to everything it calls.

**The week's solves** are one row per attempt in the window, with its outcome, minutes and main
patterns. An untagged solve still shows, with no pattern.

**The week's patterns** are every main pattern a solve in the window used, however long ago it
was first picked up. Each row shows:

- its attempts this week, and its attempts and problems all time;
- its mastery score, which is all time, because a week is too little history to judge a
  pattern on;
- its standing: `too-early` below the history floor (`mastery.enough_history`), otherwise
  `weak` or `on-track`, read only as membership in `analyze()`'s weak list
  (`service.standing_of`, shared with the note shown after logging a solve);
- `delta`: the score now minus the score folded over the same pattern's attempts before the
  window. It is the one number about the week, and `None` for a pattern first practiced in it.

Patterns are listed weak first, then on-track, then too-early, so what needs work is read first.

Nothing about the week is written down. It used to be a report file and a frozen snapshot with
an LLM narrative beside it; the snapshot went stale the moment the next solve was logged, and
the narrative restated numbers the tables already showed. The question it was there to answer,
"is this pattern getting better?", is a subtraction, and computing both scores with the same
`mastery.pattern_stats` over the same loaded history means the two sides cannot be computed two
different ways.
