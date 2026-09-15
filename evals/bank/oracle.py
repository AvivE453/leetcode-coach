"""Execution oracle for the feedback bank.

Every flaw label is produced by RUNNING the code, never by asserting that a
mutation is a defect. A mutant is labelled only if execution proves it:

  fails a test marked "general"   -> bug
  fails only tests marked "edge"  -> edge-case
  passes every test but is much   -> complexity
    slower at scale
  passes everything unchanged     -> equivalent mutant, DISCARDED

Discarding on inconclusive evidence means weak tests cost us fixtures rather
than producing mislabelled ones - the safe direction to fail.

A handful of hand-written tests is thin evidence, so two labels are checked against
the problem's brute-force `reference` on DIFFERENTIAL_CASES inputs from its `generate`,
which only produces inputs the constraints allow. A discard - and every clean control -
must agree with it everywhere; an edge-case must disagree only on inputs the problem's
`is_edge` calls edges. Neither check assigns a label: when one fails, TestsTooWeak says
which input the tests are missing, and a person adds that test and decides its kind.
"""

import copy
import random
import signal
import sys
import time
import tracemalloc
from dataclasses import dataclass

TEST_TIMEOUT = 5.0
SCALE_TIMEOUT = 10.0
COMPLEXITY_RATIO = 5.0
# A solution that finishes in microseconds is timed over repeated calls until this much
# time has accumulated, so its ratio measures the code rather than the clock's noise.
MIN_TIMED_SECONDS = 0.05
DIFFERENTIAL_CASES = 1000
# The memory check catches one thing: a control that needs megabytes at SPACE_SCALE where the
# canonical needs almost nothing - an O(n) copy beside an O(1) solution. One input size cannot
# tell a higher order from a larger constant, and a list of characters against a string, or
# lru_cache against a dict, is a constant a reviewer has no business calling a flaw.
SPACE_CANONICAL_SMALL_BYTES = 64_000
SPACE_CONTROL_LARGE_BYTES = 512_000

# LeetCode accepts a recursive DFS across its largest grids; Python's default limit of 1000
# frames would reject those solutions here for a reason the problem never imposes.
sys.setrecursionlimit(100_000)


class Timeout(Exception):
    pass


class TestsTooWeak(Exception):
    """The hand-written tests cannot justify the label the code would get."""

    def __init__(self, slug: str, counterexample: str, finding: str):
        super().__init__(f"{slug}: {finding} ({counterexample}) - add a test for that input"
                         " and decide whether it is general or edge")
        self.counterexample = counterexample


def _on_alarm(signum, frame):
    raise Timeout()


def with_timeout(fn, seconds: float):
    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def entry_point_factory(code: str, method: str):
    """exec a solution once, and return a maker of its `method` bound to a fresh Solution.

    The problem names the method, as LeetCode does, so a solution may keep helper methods
    beside it. Fresh for every input, as on LeetCode's judge, so state a solution leaves
    on `self` never leaks from one input into the next.
    """
    namespace: dict = {}
    exec(compile(code, "<fixture>", "exec"), namespace)  # noqa: S102 - our fixtures, or pinned and judged solutions
    cls = namespace.get("Solution")
    if cls is None or not callable(getattr(cls, method, None)):
        raise ValueError(f"expected a class Solution with a method {method}")
    return lambda: getattr(cls(), method)


def load_entry_point(code: str, method: str):
    """exec a solution and return its `method`, bound."""
    return entry_point_factory(code, method)()


def same(got, expected, normalize) -> bool:
    return normalize(got) == normalize(expected) if normalize else got == expected


@dataclass(frozen=True)
class TestOutcome:
    kind: str
    passed: bool
    detail: str


def run_tests(code: str, tests, method: str, normalize=None) -> list[TestOutcome]:
    fresh = entry_point_factory(code, method)
    outcomes = []
    for args, expected, kind in tests:
        try:
            got = with_timeout(lambda a=args: fresh()(*copy.deepcopy(a)), TEST_TIMEOUT)
            equal = same(got, expected, normalize)
            detail = "" if equal else f"input={args!r} expected={expected!r} got={got!r}"
        except Timeout:
            equal, detail = False, f"input={args!r} timed out"
        except Exception as exc:  # noqa: BLE001 - a crashing mutant is a failing mutant
            equal, detail = False, f"input={args!r} raised {type(exc).__name__}: {exc}"
        outcomes.append(TestOutcome(kind, equal, detail))
    return outcomes


def time_at_scale(code: str, method: str, scale_args) -> float | None:
    """Seconds one call on the scale input takes; None if a call exceeds SCALE_TIMEOUT.

    Each call gets its own copy of the input, made before the clock starts - copying a
    large fixture is constant overhead that would otherwise compress the ratio between a
    fast and a slow solution. Calls repeat until MIN_TIMED_SECONDS have been timed.
    """
    fresh = entry_point_factory(code, method)
    timed = 0.0
    calls = 0
    while timed < MIN_TIMED_SECONDS:
        fn = fresh()
        args = copy.deepcopy(scale_args)
        started = time.perf_counter()
        try:
            with_timeout(lambda fn=fn, args=args: fn(*args), SCALE_TIMEOUT)
        except Timeout:
            return None
        timed += time.perf_counter() - started
        calls += 1
    return timed / calls


def peak_memory(code: str, method: str, args) -> int:
    """Peak bytes Python allocates while the solution runs once on `args`, copied beforehand."""
    fn = load_entry_point(code, method)
    args = copy.deepcopy(args)
    tracemalloc.start()
    try:
        with_timeout(lambda: fn(*args), SCALE_TIMEOUT)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def differential_cases(problem) -> list[tuple]:
    """Generated inputs with the reference's answers, computed once per problem.

    Seeded by the problem number, so every run judges against the same inputs. Kept on the
    problem itself because a brute force is slow and one problem is judged many times: its
    canonical, each clean control, each would-be discard.
    """
    cases = getattr(problem, "_differential_cases", None)
    if cases is None:
        rng = random.Random(problem.NUMBER)
        count = getattr(problem, "DIFFERENTIAL_CASES", DIFFERENTIAL_CASES)
        inputs = [problem.generate(rng) for _ in range(count)]
        cases = [(args, problem.reference(*copy.deepcopy(args))) for args in inputs]
        problem._differential_cases = cases
    return cases


def disagreement(problem, code: str, include=None) -> str | None:
    """The first generated input - of those `include` admits - where the code does not match the reference."""
    fresh = entry_point_factory(code, problem.METHOD)
    normalize = getattr(problem, "normalize", None)
    for args, expected in differential_cases(problem):
        if include is not None and not include(args):
            continue
        try:
            got = with_timeout(lambda a=args: fresh()(*copy.deepcopy(a)), TEST_TIMEOUT)
            if not same(got, expected, normalize):
                return f"input={args!r} expected={expected!r} got={got!r}"
        except Timeout:
            return f"input={args!r} timed out"
        except Exception as exc:  # noqa: BLE001 - a crash on an allowed input is a disagreement
            return f"input={args!r} raised {type(exc).__name__}: {exc}"
    return None


@dataclass(frozen=True)
class Verdict:
    category: str | None  # None = discard (equivalent mutant)
    evidence: str


def scale_baseline(problem) -> float:
    """Seconds the canonical needs at scale - what every ratio below is measured against.

    A canonical nobody can time invalidates every complexity label for its problem,
    the same way one that fails its own tests invalidates every label, so this
    raises rather than handing back a number no ratio can be built from. Both
    unusable cases used to be swallowed by one `if baseline and ...`: too slow to
    finish came back as None, which formatted as a duration would raise TypeError
    and otherwise fell through to "indistinguishable from the canonical" - a
    discard claimed on a comparison that never happened, and the one thing this
    module says it will not do. Too fast to measure came back as 0.0 and took the
    same path, so a mutant taking nine seconds against an unmeasurable canonical
    was reported as equivalent to it.
    """
    seconds = time_at_scale(problem.CANONICAL, problem.METHOD, problem.SCALE)
    if seconds is None:
        raise AssertionError(
            f"{problem.SLUG}: canonical solution exceeded {SCALE_TIMEOUT}s at scale,"
            f" so there is nothing to measure a mutant against"
        )
    if seconds <= 0:
        raise AssertionError(
            f"{problem.SLUG}: canonical solution is too fast at scale to measure"
            f" ({seconds}s) - SCALE needs to be big enough to time"
        )
    return seconds


def classify(problem, code: str) -> Verdict:
    normalize = getattr(problem, "normalize", None)
    outcomes = run_tests(code, problem.TESTS, problem.METHOD, normalize)
    failures = [o for o in outcomes if not o.passed]

    if failures:
        if any(o.kind == "general" for o in failures):
            return Verdict("bug", failures[0].detail)
        is_edge = getattr(problem, "is_edge", None)
        if is_edge is not None:
            counterexample = disagreement(problem, code, include=lambda args: not is_edge(*args))
            if counterexample:
                raise TestsTooWeak(problem.SLUG, counterexample,
                                   "fails only edge tests, yet also an input is_edge does not call an edge")
        return Verdict("edge-case", failures[0].detail)

    baseline = scale_baseline(problem)
    mutant = time_at_scale(code, problem.METHOD, problem.SCALE)
    if mutant is None:
        return Verdict("complexity", f"exceeded {SCALE_TIMEOUT}s at scale (canonical: {baseline * 1000:.3g}ms)")
    if mutant / baseline >= COMPLEXITY_RATIO:
        return Verdict("complexity", f"{mutant / baseline:.0f}x slower at scale"
                                     f" ({mutant * 1000:.3g}ms vs {baseline * 1000:.3g}ms)")
    counterexample = disagreement(problem, code)
    if counterexample:
        raise TestsTooWeak(problem.SLUG, counterexample, "passes every test but disagrees with the reference")
    return Verdict(None, "indistinguishable from the canonical solution")


def verify_canonical(problem) -> None:
    """A canonical solution or a test that disagrees with the reference invalidates every label."""
    normalize = getattr(problem, "normalize", None)
    for args, expected, _ in problem.TESTS:
        want = problem.reference(*copy.deepcopy(args))
        if not same(want, expected, normalize):
            raise AssertionError(f"{problem.SLUG}: the test on input={args!r} expects {expected!r},"
                                 f" but the reference returns {want!r}")
    failures = [o for o in run_tests(problem.CANONICAL, problem.TESTS, problem.METHOD, normalize)
                if not o.passed]
    if failures:
        raise AssertionError(f"{problem.SLUG}: canonical solution fails its own tests: "
                             f"{failures[0].detail}")
    counterexample = disagreement(problem, problem.CANONICAL)
    if counterexample:
        raise AssertionError(f"{problem.SLUG}: canonical solution disagrees with the reference:"
                             f" {counterexample}")


def verify_clean(problem, variant) -> None:
    """A clean control the oracle cannot prove clean would score a correct report as a false positive.

    Proven clean: it passes every test, is not measurably slower than the canonical,
    agrees with the reference, and - because no timing can see it - does not need
    megabytes on SPACE_SCALE where the canonical needs almost nothing.
    """
    name = f"{problem.SLUG}/{variant['id']}"
    try:
        verdict = classify(problem, variant["code"])
    except TestsTooWeak as exc:
        raise AssertionError(f"{name}: clean variant is not clean (disagrees with the reference:"
                             f" {exc.counterexample})") from exc
    if verdict.category is not None:
        raise AssertionError(f"{name}: clean variant is not clean"
                             f" ({verdict.category}: {verdict.evidence})")
    try:
        canonical = peak_memory(problem.CANONICAL, problem.METHOD, problem.SPACE_SCALE)
    except Timeout:
        raise AssertionError(f"{problem.SLUG}: the canonical itself times out on SPACE_SCALE, so no"
                             " control's memory can be judged - SPACE_SCALE is too big") from None
    try:
        used = peak_memory(variant["code"], problem.METHOD, problem.SPACE_SCALE)
    except Timeout:
        raise AssertionError(f"{name}: clean variant is not clean (timed out on SPACE_SCALE)") from None
    if canonical <= SPACE_CANONICAL_SMALL_BYTES and used > SPACE_CONTROL_LARGE_BYTES:
        raise AssertionError(f"{name}: clean variant is not clean (peaks at {used:,} bytes on"
                             f" SPACE_SCALE, where the canonical needs {canonical:,})")
