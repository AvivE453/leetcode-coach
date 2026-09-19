/* Home page: progress numbers and the pattern table. The log form is its own page, log.html.
   el()/getJSON() come from dom.js, loaded before this script. */

/* ---------- stats ---------- */

/* The curriculum lists as people write them; the API keys them by file name. */
const CURRICULUM_LABEL = { blind75: "Blind 75", neetcode150: "NeetCode 150" };

function renderStats(s) {
  document.getElementById("hero-solved").textContent = s.solved;
  document.getElementById("hero-note").textContent =
    `${s.attempts} solution${s.attempts === 1 ? "" : "s"} submitted · ` +
    `${s.last_7_days} in the last 7 days · ${s.catalog} problems in the catalog`;

  // Same difficulty colors as the diff badges on Solutions and the Daily Plan.
  document.getElementById("hero-diff").replaceChildren(
    ...["Easy", "Medium", "Hard"].flatMap((d, i) => [
      ...(i ? [" · "] : []),
      el("span", { class: `diff ${d}`, text: `${d} ${s.by_difficulty[d]}` }),
    ])
  );

  const cards = document.getElementById("stat-cards");
  cards.replaceChildren();

  cards.append(statCard("Due for review", String(s.due_today), s.due_today ? "waiting on you today" : "nothing due"));
  cards.append(statCard("Last 7 days", String(s.last_7_days), "solutions submitted"));

  for (const [name, p] of Object.entries(s.curriculum)) {
    const label = CURRICULUM_LABEL[name] || name;
    const card = statCard(label, String(p.done), `of ${p.total}`);
    const pct = p.total ? (p.done / p.total) * 100 : 0;
    const bar = el("div", { class: "bar" }, [el("span", { style: `width:${pct}%` })]);
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `${label}: ${p.done} of ${p.total} solved`);
    card.append(bar);
    cards.append(card);
  }
}

function statCard(label, value, note) {
  return el("div", { class: "card" }, [
    el("p", { class: "k", text: label }),
    el("p", { class: "v", text: value }, note ? [el("small", { text: note })] : []),
  ]);
}

/* ---------- pattern table ---------- */

const PATTERN_COLUMNS = [
  ["Pattern", (p) => p.pattern],
  ["Problems solved", (p) => String(p.solved)],
  ["Mastery (1–5)", (p) => p.score.toFixed(1)],
  ["Solutions submitted", (p) => String(p.attempts)],
  ["Not clean", (p) => String(p.rough)],
];

function renderPatternTable(patterns) {
  const host = document.getElementById("pattern-table");
  host.replaceChildren();

  if (!patterns.length) {
    host.append(el("p", {
      class: "loading",
      text: "No tagged solutions yet — log a solve (with an API key set) and patterns appear here.",
    }));
    return;
  }

  host.append(
    el("table", {}, [
      el("thead", {}, [el("tr", {}, PATTERN_COLUMNS.map(([name]) => el("th", { text: name })))]),
      el("tbody", {}, patterns.map((p) =>
        el("tr", {}, PATTERN_COLUMNS.map(([, cell]) => el("td", { text: cell(p) })))
      )),
    ])
  );
}

/* ---------- wiring ---------- */

async function refresh() {
  const [stats, patterns] = await Promise.all([getJSON("/api/stats"), getJSON("/api/patterns")]);
  renderStats(stats);
  renderPatternTable(patterns.patterns);
}

refresh().catch((err) => {
  document.getElementById("hero-note").textContent = `Could not load stats: ${err.message}`;
});
