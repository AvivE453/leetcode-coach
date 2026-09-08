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
"""

import copy
import signal
import time
from dataclasses import dataclass

TEST_TIMEOUT = 5.0
SCALE_TIMEOUT = 10.0
COMPLEXITY_RATIO = 5.0


class Timeout(Exception):
    pass


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


def load_entry_point(code: str):
    """exec a fixture solution and return its single public method, bound."""
    namespace: dict = {}
    exec(compile(code, "<fixture>", "exec"), namespace)  # noqa: S102 - fixtures are our own code
    cls = namespace["Solution"]
    methods = [name for name in vars(cls) if not name.startswith("_")]
    if len(methods) != 1:
        raise ValueError(f"expected exactly one public method on Solution, got {methods}")
    return getattr(cls(), methods[0])


@dataclass(frozen=True)
class TestOutcome:
    kind: str
    passed: bool
    detail: str


def run_tests(code: str, tests, normalize=None) -> list[TestOutcome]:
    fn = load_entry_point(code)
    outcomes = []
    for args, expected, kind in tests:
        try:
            got = with_timeout(lambda a=args: fn(*copy.deepcopy(a)), TEST_TIMEOUT)
            equal = normalize(got) == normalize(expected) if normalize else got == expected
            detail = "" if equal else f"input={args!r} expected={expected!r} got={got!r}"
        except Timeout:
            equal, detail = False, f"input={args!r} timed out"
        except Exception as exc:  # noqa: BLE001 - a crashing mutant is a failing mutant
            equal, detail = False, f"input={args!r} raised {type(exc).__name__}: {exc}"
        outcomes.append(TestOutcome(kind, equal, detail))
    return outcomes


def time_at_scale(code: str, scale_args) -> float | None:
    """Seconds to run one scale input; None if it exceeds SCALE_TIMEOUT.

    The input is copied before the clock starts - copying a large fixture is
    constant overhead that would otherwise compress the ratio between a fast
    and a slow solution.
    """
    fn = load_entry_point(code)
    args = copy.deepcopy(scale_args)
    started = time.perf_counter()
    try:
        with_timeout(lambda: fn(*args), SCALE_TIMEOUT)
    except Timeout:
        return None
    return time.perf_counter() - started


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
    seconds = time_at_scale(problem.CANONICAL, problem.SCALE)
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
    normalize = getattr(problem, "NORMALIZE", None)
    outcomes = run_tests(code, problem.TESTS, normalize)
    failures = [o for o in outcomes if not o.passed]

    if failures:
        category = "bug" if any(o.kind == "general" for o in failures) else "edge-case"
        return Verdict(category, failures[0].detail)

    baseline = scale_baseline(problem)
    mutant = time_at_scale(code, problem.SCALE)
    if mutant is None:
        return Verdict("complexity", f"exceeded {SCALE_TIMEOUT}s at scale (canonical: {baseline:.3f}s)")
    if mutant / baseline >= COMPLEXITY_RATIO:
        return Verdict("complexity", f"{mutant / baseline:.0f}x slower at scale"
                                     f" ({mutant:.3f}s vs {baseline:.3f}s)")
    return Verdict(None, "indistinguishable from the canonical solution")


def verify_canonical(problem) -> None:
    """A canonical solution that fails its own tests invalidates every label."""
    normalize = getattr(problem, "NORMALIZE", None)
    failures = [o for o in run_tests(problem.CANONICAL, problem.TESTS, normalize) if not o.passed]
    if failures:
        raise AssertionError(f"{problem.SLUG}: canonical solution fails its own tests: "
                             f"{failures[0].detail}")
