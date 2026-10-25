# Practice history

Everything the coach computes about your practice (mastery, the review schedule, approach
practice, the daily plan and the weekly review) reads the history through one function,
`history.load` in [coach/history.py](../coach/history.py). It used to be four queries in four
modules, each with its own join, its own JSON decoding and its own choice of inner or left join,
so a change to how a review attaches to a solve meant editing all four, and missing one made
them disagree with nothing to fail.

## An attempt

`load` returns a list of `Attempt`s: one per solve, seen as practice.

- **The solve as logged**: its id (the `solution_id` the tags, review and vector are keyed by),
  day, outcome, minutes, and whether the problem was due that day.
- **Its problem**, with the problem's accepted approaches (`enrich.Canonical`), carried on the
  attempt so approach practice needs no second query.
- **Its tags**, when it has been tagged. `main_patterns` is `None` until then: unknown, which is
  never evidence, and not the same as an empty list.
- **Its review**, when one was bought: the verdict and the issues.
- **Two derived values**, computed on read and never stored: `grade`, the 1-5 grade the solve
  earned (its outcome, capped by what its review found), and `finding`, the worst correctness
  problem its review reports. Both come from [coach/assessment.py](../coach/assessment.py), the one
  owner of what a review does to a solve.

`Attempt` and `Problem` are frozen dataclasses holding tuples, so the readers that share one
list cannot change it under each other.

## The query

```sql
FROM solutions s
JOIN problems p ON p.number = s.problem_number
LEFT JOIN enrichments en ON en.solution_id = s.id
LEFT JOIN reviews rv ON rv.solution_id = s.id
WHERE :number IS NULL OR p.number = :number
ORDER BY s.date, s.id
```

- **Solves drive the join.** Tags and reviews are left-joined, because a solve logged before
  enrichment ran is still practice that happened, and an inner join would drop it and quietly
  change what the schedule replays.
- **One query for both uses.** With no `number` it reads every solve; with one it reads that
  problem's, which is what replaying one problem's schedule needs.
- **Oldest first, across every problem**, because that is the order mastery folds scores in. Two
  solves on the same day keep the order they were logged in (`s.id`). `by_problem` groups the
  list by problem without re-sorting it.

## One load per request, pure functions over it

Mastery (`mastery.scored`), approach practice (`corrections.owed`), review findings
(`assessment.findings`) and the weekly window (`weekly_collect.window`) take the attempts as an
argument and never touch the database. A request loads the history once and hands the same list
to all of them, so they always judge the same evidence, and each can be tested with a list built
in memory.

Nothing is cached: a review saved days after the solve it judges, or a tag backfilled by
`coach enrich`, counts on the next read. On the real history (185 solves, October 2026) the
whole read takes about 2 ms.
