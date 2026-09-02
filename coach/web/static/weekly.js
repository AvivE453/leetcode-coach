/* Weekly Review page: the last `coach weekly` run, frozen as it was written. */

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

function renderEmpty() {
  document.getElementById("note").replaceChildren(
    el("p", { class: "empty", text: "No weekly run yet — `coach weekly` runs every Sunday on this machine." }),
    el("p", {
      class: "hint",
      text: "Run it by hand any time with `coach weekly`; the note it writes shows up here.",
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

function withScore(scores) {
  /* Pattern name plus the mastery it had that week, when the run recorded one. */
  return (pattern) =>
    el("li", {
      text: scores[pattern] === undefined ? pattern : `${pattern} — ${scores[pattern].toFixed(1)}/5`,
    });
}

function renderSnapshot(run) {
  const s = run.stats;
  const scores = s.pattern_scores || {};
  document.getElementById("snapshot-section").hidden = false;

  document.getElementById("counts").replaceChildren(
    countCard("Attempts that week", s.attempts),
    countCard("Distinct problems", s.distinct_problems),
    countCard("Reviews due", s.due),
    countCard("Problems planned", s.planned)
  );

  document.getElementById("snapshot-topics").replaceChildren(
    topicCard(
      "Weak patterns",
      "Nothing was flagged weak that week.",
      s.weak_patterns || [],
      withScore(scores)
    ),
    topicCard(
      "Stale patterns",
      "Nothing had gone stale (30+ days untouched).",
      s.stale_patterns || [],
      withScore(scores)
    ),
    topicCard(
      "Solved off-pattern",
      "Every solved problem used its canonical approach.",
      s.off_pattern || [],
      (n) => el("li", { text: `#${n}` })
    )
  );
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
