"""Eval runner. Makes real API calls - costs real money, never runs in CI.

    uv run python -m evals.run_evals --all
    uv run python -m evals.run_evals --feedback
    uv run python -m evals.run_evals --enrichment --retrieval

Enrichment results are cached per (slug, prompt_version) so the retrieval eval
and repeat runs don't re-pay for them; --refresh-cache forces a re-run.
"""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from coach import config, embed, enrich, llm, review
from evals import corpus, pairs
from evals.bank import oracle
from evals.bank.problems import load_all

EVALS_DIR = Path(__file__).resolve().parent
CACHE_DIR = EVALS_DIR / "cache"
RESULTS_PATH = EVALS_DIR / "RESULTS.md"
WORKERS = 8
TOP_K = 5

# Rough observed cost of one eval call, for --dry-run. Dominated by output
# tokens, since thinking is billed as output.
COST_PER_CALL = {
    "claude-opus-5": 0.065,
    "claude-sonnet-5": 0.026,
    "claude-haiku-4-5": 0.013,
}


def parallel(fn, items, label):
    print(f"  {label}: {len(items)} call(s) ...", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(fn, items))


# ---------------------------------------------------------------- feedback


def build_bank():
    """Every fixture with an execution-derived label. Clean controls included."""
    fixtures = []
    for problem in load_all():
        oracle.verify_canonical(problem)
        fixtures.append({
            "slug": problem.SLUG,
            "id": "canonical",
            "category": None,  # clean control
            "code": problem.CANONICAL,
            "problem": problem,
        })
        for mutant in problem.MUTANTS:
            verdict = oracle.classify(problem, mutant["code"])
            if verdict.category is None:
                continue
            fixtures.append({
                "slug": problem.SLUG,
                "id": mutant["id"],
                "category": verdict.category,
                "evidence": verdict.evidence,
                "code": mutant["code"],
                "problem": problem,
            })
    return fixtures


def review_cache_path(model: str) -> Path:
    return CACHE_DIR / f"reviews-{review.PROMPT_VERSION}-{model}.json"


def run_feedback(refresh: bool, model: str) -> dict:
    print("\n[feedback] labelling fixtures by execution ...")
    fixtures = build_bank()
    flawed = [f for f in fixtures if f["category"]]
    clean = [f for f in fixtures if not f["category"]]
    print(f"  {len(flawed)} flawed + {len(clean)} clean controls")

    # Cached per prompt version and fixture, so correcting a LABEL (which changes
    # scoring, not the model's answer) costs nothing to re-score.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = review_cache_path(model)
    cached = json.loads(path.read_text()) if path.exists() and not refresh else {}

    def review_one(fixture):
        problem = fixture["problem"]
        row = {
            "number": problem.NUMBER,
            "title": problem.TITLE,
            "difficulty": problem.DIFFICULTY,
        }
        try:
            result = review.review_solution(row, fixture["code"], model=model)
        except llm.LLMUnavailable as exc:
            print(f"    !! {fixture['slug']}/{fixture['id']}: {exc}")
            return fixture["key"], None
        return fixture["key"], {
            "issues": [{"category": i.category, "description": i.description}
                       for i in result.issues],
            "verdict": result.verdict,
        }

    # Keyed by code digest too: editing a fixture must invalidate its cached review.
    for fixture in fixtures:
        digest = hashlib.sha256(fixture["code"].encode()).hexdigest()[:8]
        fixture["key"] = f"{fixture['slug']}/{fixture['id']}@{digest}"
    todo = [f for f in fixtures if f["key"] not in cached]
    if todo:
        for key, result in parallel(review_one, todo, "reviewing"):
            if result is not None:
                cached[key] = result
        path.write_text(json.dumps(cached, indent=2, sort_keys=True))
    else:
        print(f"  reviews: all {len(fixtures)} cached for {review.PROMPT_VERSION}"
              f" on {model}, no calls made")

    results = [cached.get(f["key"]) for f in fixtures]

    per_category: dict[str, list[bool]] = {}
    misses = []
    for fixture, result in zip(fixtures, results):
        if result is None or not fixture["category"]:
            continue
        found = {issue["category"] for issue in result["issues"]}
        caught = fixture["category"] in found
        per_category.setdefault(fixture["category"], []).append(caught)
        if not caught:
            misses.append(f"{fixture['slug']}/{fixture['id']} "
                          f"(planted {fixture['category']}, reported {sorted(found) or 'nothing'})")

    false_positives = []
    optimal_verdicts = 0
    scored_clean = 0
    for fixture, result in zip(fixtures, results):
        if result is None or fixture["category"]:
            continue
        scored_clean += 1
        if result["issues"]:
            false_positives.append(f"{fixture['slug']} "
                                   f"({', '.join(i['category'] for i in result['issues'])})")
        if result["verdict"] == "optimal":
            optimal_verdicts += 1

    recall = {c: sum(v) / len(v) for c, v in sorted(per_category.items())}
    all_flags = [x for v in per_category.values() for x in v]
    return {
        "prompt_version": review.PROMPT_VERSION,
        "fixtures": len(fixtures),
        "recall_by_category": recall,
        "recall_overall": sum(all_flags) / len(all_flags) if all_flags else 0.0,
        "counts": {c: len(v) for c, v in sorted(per_category.items())},
        "false_positive_rate": len(false_positives) / scored_clean if scored_clean else 0.0,
        "clean_controls": scored_clean,
        "optimal_verdict_rate": optimal_verdicts / scored_clean if scored_clean else 0.0,
        "misses": misses,
        "false_positives": false_positives,
    }


# -------------------------------------------------------------- enrichment


def cache_path(model: str) -> Path:
    return CACHE_DIR / f"enrichment-{enrich.PROMPT_VERSION}-{model}.json"


def enrich_corpus(refresh: bool, model: str) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(model)
    cached = json.loads(path.read_text()) if path.exists() and not refresh else {}

    entries = corpus.load()
    todo = [e for e in entries if e.slug not in cached]
    if todo:
        def enrich_one(entry):
            row = {
                "number": entry.number,
                "title": entry.title,
                "difficulty": entry.difficulty,
                "official_tags": entry.official_tags,
            }
            try:
                return entry.slug, review_safe_enrich(row, entry.code, model)
            except llm.LLMUnavailable as exc:
                print(f"    !! {entry.slug}: {exc}")
                return entry.slug, None

        for slug, result in parallel(enrich_one, todo, "enriching corpus"):
            if result is not None:
                cached[slug] = result
        path.write_text(json.dumps(cached, indent=2, sort_keys=True))
    else:
        print(f"  enrichment: {len(entries)} cached, no calls made")
    return cached


def review_safe_enrich(row, code, model) -> dict:
    e = enrich.enrich_solution(row, code, model=model)
    return {
        "pattern": e.pattern,
        "intended_pattern": e.intended_pattern,
        # Recorded but not scored: enrich-v3 added it, and the corpus labels only
        # cover the central intended_pattern (see RESULTS.md).
        "intended_secondary_patterns": e.intended_secondary_patterns,
        "secondary_patterns": e.secondary_patterns,
        "key_trick": e.key_trick,
        "time_complexity": e.time_complexity,
        "space_complexity": e.space_complexity,
    }


def run_enrichment(cached: dict) -> dict:
    entries = corpus.load()
    hits = agree = scored = 0
    wrong = []
    for entry in entries:
        result = cached.get(entry.slug)
        if result is None:
            continue
        scored += 1
        if result["intended_pattern"] in entry.accept:
            hits += 1
        else:
            wrong.append(f"{entry.slug}: said {result['intended_pattern']}, "
                         f"accepted {list(entry.accept)}")
        if result["pattern"] == result["intended_pattern"]:
            agree += 1
    return {
        "prompt_version": enrich.PROMPT_VERSION,
        "scored": scored,
        "intended_accuracy": hits / scored if scored else 0.0,
        "canonical_agreement": agree / scored if scored else 0.0,
        "wrong": wrong,
    }


# --------------------------------------------------------------- retrieval


def recall_at_k(vectors: dict[str, np.ndarray], k: int) -> tuple[float, list[str]]:
    slugs = list(vectors)
    matrix = np.stack([vectors[s] for s in slugs])
    index = {s: i for i, s in enumerate(slugs)}

    hits = 0
    total = 0
    missed = []
    for a, b in pairs.SIMILAR_PAIRS:
        if a not in index or b not in index:
            continue
        for query, want in ((a, b), (b, a)):
            total += 1
            scores = matrix @ vectors[query]
            scores[index[query]] = -np.inf
            top = {slugs[i] for i in np.argsort(-scores)[:k]}
            if want in top:
                hits += 1
            else:
                missed.append(f"{query} -> {want}")
    return (hits / total if total else 0.0), missed


def run_retrieval(cached: dict) -> dict:
    entries = [e for e in corpus.load() if e.slug in cached]
    print(f"  embedding {len(entries)} solutions two ways (local, no API calls)")

    raw = embed.encode([e.code for e in entries])
    cards = embed.encode([
        embed.card_text(e.title, cached[e.slug]["pattern"], cached[e.slug]["key_trick"], e.code)
        for e in entries
    ])

    raw_recall, raw_missed = recall_at_k({e.slug: v for e, v in zip(entries, raw)}, TOP_K)
    card_recall, card_missed = recall_at_k({e.slug: v for e, v in zip(entries, cards)}, TOP_K)
    return {
        "corpus_size": len(entries),
        "pair_directions": 2 * len(pairs.SIMILAR_PAIRS),
        "raw_code_recall_at_5": raw_recall,
        "enriched_card_recall_at_5": card_recall,
        "delta": card_recall - raw_recall,
        "card_misses": card_missed,
        "raw_misses": raw_missed,
    }


# ------------------------------------------------------------------ report


def append_results(sections: dict, model: str) -> None:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"\n## {stamp} · model `{model}`\n"]

    if "feedback" in sections:
        f = sections["feedback"]
        lines.append(f"### Feedback quality — prompt `{f['prompt_version']}`\n")
        lines.append("| Metric | Value | n |")
        lines.append("|---|---|---|")
        for category, value in f["recall_by_category"].items():
            lines.append(f"| recall · {category} | {value:.0%} | {f['counts'][category]} |")
        lines.append(f"| **recall · overall** | **{f['recall_overall']:.0%}** |"
                     f" {sum(f['counts'].values())} |")
        lines.append(f"| **false-positive rate** (clean controls) |"
                     f" **{f['false_positive_rate']:.0%}** | {f['clean_controls']} |")
        lines.append(f"| verdict `optimal` on clean controls | {f['optimal_verdict_rate']:.0%} |"
                     f" {f['clean_controls']} |")
        lines.append("")
        if f["misses"]:
            lines.append("Missed flaws: " + "; ".join(f["misses"]) + "\n")
        if f["false_positives"]:
            lines.append("False positives: " + "; ".join(f["false_positives"]) + "\n")

    if "enrichment" in sections:
        e = sections["enrichment"]
        lines.append(f"### Enrichment — prompt `{e['prompt_version']}`\n")
        lines.append("| Metric | Value | n |")
        lines.append("|---|---|---|")
        lines.append(f"| `intended_pattern` accuracy (vs NeetCode sections) |"
                     f" **{e['intended_accuracy']:.0%}** | {e['scored']} |")
        lines.append(f"| solution pattern == intended, on canonical code |"
                     f" {e['canonical_agreement']:.0%} | {e['scored']} |")
        lines.append("")
        if e["wrong"]:
            lines.append("Disagreements: " + "; ".join(e["wrong"]) + "\n")

    if "retrieval" in sections:
        r = sections["retrieval"]
        lines.append("### Retrieval — recall@5\n")
        lines.append("| Embedding input | recall@5 |")
        lines.append("|---|---|")
        lines.append(f"| raw code | {r['raw_code_recall_at_5']:.0%} |")
        lines.append(f"| enriched card | **{r['enriched_card_recall_at_5']:.0%}** |")
        lines.append(f"| delta | {r['delta']:+.0%} |")
        lines.append(f"\n{r['corpus_size']} solutions, {r['pair_directions']} labelled"
                     f" pair directions.\n")
        if r["card_misses"]:
            lines.append("Card misses: " + "; ".join(r["card_misses"]) + "\n")

    header = ""
    if not RESULTS_PATH.exists():
        header = ("# Eval results\n\nAppend-only. Each run records the prompt versions it"
                  " scored, so a prompt change can be read as a movement in these numbers.\n"
                  "\nGround truth: feedback labels come from executing each mutant against a"
                  " test harness (`evals/bank/oracle.py`); enrichment labels come from"
                  " NeetCode's published Blind 75 sections; retrieval pairs are hand-labelled"
                  " in `evals/pairs.py`.\n")
    with RESULTS_PATH.open("a") as fh:
        fh.write(header + "\n".join(lines) + "\n")
    print(f"\nAppended to {RESULTS_PATH.relative_to(config.PROJECT_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feedback", action="store_true")
    parser.add_argument("--enrichment", action="store_true")
    parser.add_argument("--retrieval", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--model", default=config.EVAL_MODEL,
                        help=f"Model to score (default: {config.EVAL_MODEL}). Pass"
                             f" {config.MODEL} to score the model the coach itself uses.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would run and how many calls it costs")
    args = parser.parse_args()

    want_feedback = args.feedback or args.all
    want_enrichment = args.enrichment or args.all
    want_retrieval = args.retrieval or args.all
    if not (want_feedback or want_enrichment or want_retrieval or args.dry_run):
        parser.error("pick at least one of --feedback / --enrichment / --retrieval / --all")

    if args.dry_run:
        reviews = len(build_bank()) if want_feedback or args.all else 0
        enrichments = len(corpus.load()) if want_enrichment or want_retrieval or args.all else 0
        cached_reviews = review_cache_path(args.model)
        cached_enrich = cache_path(args.model)
        if cached_reviews.exists() and not args.refresh_cache:
            reviews = max(0, reviews - len(json.loads(cached_reviews.read_text())))
        if cached_enrich.exists() and not args.refresh_cache:
            enrichments = max(0, enrichments - len(json.loads(cached_enrich.read_text())))
        total = reviews + enrichments
        print(f"model: {args.model}")
        print(f"feedback: {reviews} review call(s) not already cached")
        print(f"enrichment: {enrichments} enrichment call(s) not already cached")
        print("retrieval: 0 API calls (local embeddings, reuses the enrichment cache)")
        print(f"\ntotal: {total} call(s), roughly ${total * COST_PER_CALL[args.model]:.2f}"
              if args.model in COST_PER_CALL else f"\ntotal: {total} call(s)")
        return 0

    if not llm.have_api_key():
        print("ANTHROPIC_API_KEY is not set - add it to .env at the project root.")
        return 1

    sections = {}
    if want_feedback:
        sections["feedback"] = run_feedback(args.refresh_cache, args.model)
    if want_enrichment or want_retrieval:
        print("\n[enrichment] corpus ...")
        cached = enrich_corpus(args.refresh_cache, args.model)
        if want_enrichment:
            sections["enrichment"] = run_enrichment(cached)
        if want_retrieval:
            print("\n[retrieval] ...")
            sections["retrieval"] = run_retrieval(cached)

    print("\n" + json.dumps(sections, indent=2, default=str))
    append_results(sections, args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
