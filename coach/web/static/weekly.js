/* Weekly Review page: the last seven days, recomputed on every load.

Nothing here is stored - /api/weekly runs the same SQL the CLI does, so this
page is current the moment a solve is logged. Mastery and standing are all-time
numbers; only `delta` is about this week, and it is the difference between the
score now and the same score folded over history up to the window's start. */

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

function score(value) {
  return value == null ? "—" : `${value.toFixed(1)}/5`;
}

/* The week's movement, signed. "new" means this pattern had no history before
   the window, so there is nothing to compare it against. */
function trend(delta) {
  if (delta == null) return "new";
  if (Math.abs(delta) < 0.05) return "±0.0";
  return `${delta > 0 ? "+" : "−"}${Math.abs(delta).toFixed(1)}`;
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
          el("td", { text: r.pattern || "untagged" }),
        ])
      )
    ),
  ]);
}

const STANDING_LABEL = { weak: "needs work", "on-track": "going well", "too-early": "too early to call" };

function patternsTable(patterns) {
  return el("table", {}, [
    el(
      "thead",
      {},
      ["Pattern", "This week", "All-time", "Mastery", "Change", "Standing"].map((h) => el("th", { text: h }))
    ),
    el(
      "tbody",
      {},
      patterns.map((p) =>
        el("tr", {}, [
          el("td", { text: p.pattern }),
          el("td", { text: String(p.attempts_week) }),
          el("td", { text: String(p.attempts_total) }),
          el("td", { text: score(p.score) }),
          el("td", { text: trend(p.delta) }),
          el("td", {}, [el("span", { class: `standing ${p.standing}`, text: STANDING_LABEL[p.standing] })]),
        ])
      )
    ),
  ]);
}

function verdictItem(p) {
  return el("li", { text: `${p.pattern} — ${score(p.score)} (${trend(p.delta)})` });
}

function renderWeek(data) {
  document.getElementById("week-meta").textContent = `${data.start} to ${data.end}`;

  document.getElementById("counts").replaceChildren(
    countCard("Attempts", data.attempts.length),
    countCard("Distinct problems", data.distinct_problems),
    countCard("Patterns used", data.patterns.length)
  );

  const host = document.getElementById("week-table");
  if (!data.attempts.length) {
    host.replaceChildren(
      el("div", { class: "card" }, [
        el("p", { class: "empty", text: "Nothing logged in the last seven days." }),
      ])
    );
    return;
  }
  host.replaceChildren(weekTable(data.attempts));
}

function renderPatterns(data) {
  const th = data.thresholds || {};
  const judged = `A pattern is judged once it has ${th.weak_min_attempts} attempts all-time; below ${th.weak_score}/5 it needs work.`;
  document.getElementById("patterns-hint").textContent =
    `Mastery is all-time, so a week of practice moves it rather than defining it. ${judged}`;

  const verdicts = document.getElementById("verdicts");
  const table = document.getElementById("patterns-table");

  if (!data.patterns.length) {
    verdicts.replaceChildren(
      el("div", { class: "card" }, [
        el("p", {
          class: "empty",
          text: "No tagged solves this week yet — patterns show up here once a solve is enriched.",
        }),
      ])
    );
    table.replaceChildren();
    return;
  }

  verdicts.replaceChildren(
    topicCard(
      "Needs more work",
      `Nothing you practiced this week is below ${th.weak_score}/5.`,
      data.patterns.filter((p) => p.standing === "weak"),
      verdictItem
    ),
    topicCard(
      "Going well",
      `Nothing yet — a pattern needs ${th.weak_min_attempts} attempts before this page will call it either way.`,
      data.patterns.filter((p) => p.standing === "on-track"),
      verdictItem
    )
  );
  table.replaceChildren(patternsTable(data.patterns));
}

async function load() {
  try {
    const res = await fetch("/api/weekly");
    if (!res.ok) throw new Error(`the coach returned ${res.status}`);
    const data = await res.json();
    renderWeek(data);
    renderPatterns(data);
  } catch (err) {
    document.getElementById("week-table").replaceChildren(
      el("p", { class: "error", text: `Could not load this week: ${err.message}` })
    );
  }
}

load();
