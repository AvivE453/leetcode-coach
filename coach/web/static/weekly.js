/* Weekly Review page: the last seven days, recomputed on every load.

Nothing here is stored - /api/weekly runs the same SQL the CLI does, so this
page is current the moment a solve is logged. Mastery and standing are all-time
numbers; only `delta` is about this week, and it is the difference between the
score now and the same score folded over history up to the window's start.

el()/getJSON()/topicCard() come from dom.js, loaded before this script. */

function countCard(label, value) {
  return el("div", { class: "card" }, [
    el("p", { class: "k", text: label }),
    el("p", { class: "v", text: String(value ?? 0) }),
  ]);
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

  // An empty card has two very different causes, and saying the wrong one misleads
  // exactly the reader who can least afford it. With nothing judged yet, "nothing
  // is below the line" reads as reassurance while the table underneath shows a
  // mastery well below it - so until at least one pattern is judged, both cards
  // say only that, and neither claims anything about the scores.
  const anyJudged = data.patterns.some((p) => p.standing !== "too-early");
  const tooEarly = "Not enough history yet.";

  verdicts.replaceChildren(
    topicCard(
      "Needs more work",
      anyJudged ? "Nothing you practiced this week needs work." : tooEarly,
      data.patterns.filter((p) => p.standing === "weak"),
      verdictItem
    ),
    topicCard(
      "Going well",
      anyJudged ? "Nothing you practiced this week is there yet." : tooEarly,
      data.patterns.filter((p) => p.standing === "on-track"),
      verdictItem
    )
  );
  table.replaceChildren(patternsTable(data.patterns));
}

async function load() {
  try {
    const data = await getJSON("/api/weekly");
    renderWeek(data);
    renderPatterns(data);
  } catch (err) {
    document.getElementById("week-table").replaceChildren(
      el("p", { class: "error", text: `Could not load this week: ${err.message}` })
    );
  }
}

load();
