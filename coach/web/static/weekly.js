/* Weekly Review page: the last weekly run, frozen as it was written.

Rows written before this depth existed only carry the thin fields (counts,
weak/stale pattern names, pattern_scores, bare off-pattern numbers) - every
section below falls back to exactly what it showed before rather than
breaking, so an old run still renders correctly. Old rows may also carry a
`plan_items` list from when the report planned the following week; it is
ignored now that `coach today` owns that. */

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of children) node.append(child);
  return node;
}

function countCard(label, value) {
  return el("div", { class: "card" }, [
    el("p", { class: "k", text: label }),
    el("p", { class: "v", text: String(value ?? 0) }),
  ]);
}

function topicCard(title, hint, items, render) {
  const card = el("div", { class: "card" }, [el("p", { class: "k", text: title })]);
  if (!items.length) {
    card.append(el("p", { class: "empty", text: hint }));
    return card;
  }
  card.append(el("ul", {}, items.map(render)));
  return card;
}

function withScore(scores) {
  /* Old-shape fallback: pattern name plus the score the run recorded, if any. */
  return (pattern) =>
    el("li", {
      text: scores[pattern] === undefined ? pattern : `${pattern} — ${scores[pattern].toFixed(1)}/5`,
    });
}

function offPatternItem(entry) {
  /* New shape is {number, title, intended_pattern}; old rows stored bare numbers. */
  if (entry !== null && typeof entry === "object") {
    return el("li", { text: `#${entry.number} ${entry.title} → ${entry.intended_pattern}` });
  }
  return el("li", { text: `#${entry}` });
}

function weekTable(rows) {
  return el("table", {}, [
    el("thead", {}, [
      el(
        "tr",
        {},
        ["Date", "Problem", "Difficulty", "Outcome", "Minutes", "Pattern"].map((h) => el("th", { text: h }))
      ),
    ]),
    el(
      "tbody",
      {},
      rows.map((r) =>
        el("tr", {}, [
          el("td", { text: r.date }),
          el("td", { text: `#${r.number} ${r.title}` }),
          el("td", {}, [el("span", { class: `diff ${r.difficulty}`, text: r.difficulty })]),
          el("td", { text: r.outcome }),
          el("td", { text: r.minutes == null ? "" : String(r.minutes) }),
          el("td", { text: r.pattern || "" }),
        ])
      )
    ),
  ]);
}

function patternsTable(patterns) {
  return el("table", {}, [
    el(
      "thead",
      {},
      ["Pattern", "Attempts", "Struggle rate", "Mastery", "Flags"].map((h) => el("th", { text: h }))
    ),
    el(
      "tbody",
      {},
      patterns.map((p) => {
        const flags = [];
        if (p.weak) flags.push("weak");
        if (p.stale) flags.push("stale");
        return el("tr", {}, [
          el("td", { text: p.pattern }),
          el("td", { text: String(p.attempts) }),
          el("td", { text: `${Math.round(p.struggle_rate * 100)}%` }),
          el("td", { text: p.score == null ? "—" : `${p.score.toFixed(1)}/5` }),
          el("td", { text: flags.join(", ") }),
        ]);
      })
    ),
  ]);
}

function curriculumCard(curriculum) {
  const entries = Object.entries(curriculum || {});
  return topicCard(
    "Curriculum",
    "No curriculum progress recorded for this run.",
    entries,
    ([name, p]) => el("li", { text: `${name}: ${p.done}/${p.total}` })
  );
}

function renderEmpty() {
  document.getElementById("note").replaceChildren(
    el("p", { class: "empty", text: "No weekly run yet — the first `coach today` of the week writes one." }),
    el("p", {
      class: "hint",
      text: "You can also run `coach weekly` by hand; the note it writes shows up here.",
    })
  );
  document.getElementById("run-meta").textContent = "";
}

function renderNote(run) {
  const host = document.getElementById("note");
  host.replaceChildren();

  if (run.narrative) {
    host.append(el("p", { class: "narrative", text: run.narrative }));
  } else {
    host.append(
      el("p", {
        class: "empty",
        text: "This run was generated without a narrative — the model was unavailable, so the numbers below are all it wrote.",
      })
    );
  }

  const meta = [`week ${run.week}`, `generated ${run.generated_at}`];
  if (run.report_path) meta.push(run.report_path);
  document.getElementById("run-meta").textContent = meta.join(" · ");
}

function renderSnapshot(run) {
  const s = run.stats;
  document.getElementById("snapshot-section").hidden = false;

  document.getElementById("counts").replaceChildren(
    countCard("Attempts that week", s.attempts),
    countCard("Distinct problems", s.distinct_problems),
    countCard("Reviews due", s.due)
  );

  const hasFullPatterns = Array.isArray(s.patterns) && s.patterns.length > 0;

  if (Array.isArray(s.attempts_detail) && s.attempts_detail.length) {
    document.getElementById("week-heading").hidden = false;
    document.getElementById("week-table").replaceChildren(weekTable(s.attempts_detail));
  } else {
    document.getElementById("week-heading").hidden = true;
    document.getElementById("week-table").replaceChildren();
  }

  if (hasFullPatterns) {
    document.getElementById("patterns-heading").hidden = false;
    document.getElementById("patterns-table").replaceChildren(patternsTable(s.patterns));
  } else {
    document.getElementById("patterns-heading").hidden = true;
    document.getElementById("patterns-table").replaceChildren();
  }

  const topics = [];
  if (!hasFullPatterns) {
    // Old-shape fallback: exactly what this page showed before the full table existed.
    const scores = s.pattern_scores || {};
    topics.push(
      topicCard("Weak patterns", "Nothing was flagged weak that week.", s.weak_patterns || [], withScore(scores)),
      topicCard(
        "Stale patterns",
        "Nothing had gone stale (30+ days untouched).",
        s.stale_patterns || [],
        withScore(scores)
      )
    );
  }
  topics.push(
    topicCard(
      "Solved off-pattern",
      "Every solved problem used its canonical approach.",
      s.off_pattern || [],
      offPatternItem
    )
  );
  if (s.curriculum) topics.push(curriculumCard(s.curriculum));
  document.getElementById("snapshot-topics").replaceChildren(...topics);
}

async function load() {
  try {
    const res = await fetch("/api/weekly");
    if (!res.ok) throw new Error(`the coach returned ${res.status}`);
    const { run } = await res.json();
    if (!run) {
      renderEmpty();
      return;
    }
    renderNote(run);
    renderSnapshot(run);
  } catch (err) {
    document.getElementById("note").replaceChildren(
      el("p", { class: "error", text: `Could not load the weekly run: ${err.message}` })
    );
  }
}

load();
