/* Home page: progress numbers, the pattern table, and the log form.
   el()/getJSON() come from dom.js, loaded before this script. */

/* ---------- stats ---------- */

function renderStats(s) {
  document.getElementById("hero-solved").textContent = s.solved;
  document.getElementById("hero-note").textContent =
    `${s.attempts} attempt${s.attempts === 1 ? "" : "s"} logged · ` +
    `${s.last_7_days} in the last 7 days · ${s.catalog} problems in the catalog`;

  const cards = document.getElementById("stat-cards");
  cards.replaceChildren();

  cards.append(statCard("Due for review", String(s.due_today), s.due_today ? "waiting on you today" : "nothing due"));
  cards.append(statCard("Last 7 days", String(s.last_7_days), "attempts"));

  const clean = (s.outcomes.find((o) => o.outcome === "clean") || { count: 0 }).count;
  const rate = s.attempts ? Math.round((clean / s.attempts) * 100) : 0;
  const breakdown = s.outcomes.map((o) => `${o.outcome} ${o.count}`).join(" · ");
  cards.append(statCard("Clean solves", `${rate}%`, breakdown || "no attempts yet"));

  for (const [name, p] of Object.entries(s.curriculum)) {
    const card = statCard(name, String(p.done), `of ${p.total}`);
    const pct = p.total ? (p.done / p.total) * 100 : 0;
    const bar = el("div", { class: "bar" }, [el("span", { style: `width:${pct}%` })]);
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `${name}: ${p.done} of ${p.total} solved`);
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

/* Practice columns are null for a pattern only ever credited as a secondary
   approach - no solve led with it, so there is nothing to measure. */
function orDash(value, format = String) {
  return value === null ? "—" : format(value);
}

const PATTERN_COLUMNS = [
  ["Pattern", (p) => p.pattern],
  ["Problems solved", (p) => String(p.solved)],
  ["Mastery (1–5)", (p) => orDash(p.score, (v) => v.toFixed(1))],
  ["Attempts", (p) => orDash(p.attempts)],
  ["Not clean", (p) => orDash(p.rough)],
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

/* ---------- log form ---------- */

function outcomeValue() {
  return document.querySelector('input[name="outcome"]:checked').value;
}

/* Minutes and note are optional: blank means "not recorded" and is sent as null.
   badInput catches text a number field shows but reports as an empty value. */
function optionalFields() {
  const minutesInput = document.getElementById("minutes");
  const raw = minutesInput.value.trim();
  const minutes = raw === "" ? null : Number(raw);
  const valid = !minutesInput.validity.badInput &&
    (minutes === null || (Number.isInteger(minutes) && minutes >= 0));
  const note = document.getElementById("note").value.trim() || null;
  return { valid, minutes, note };
}

function showError(message) {
  const box = document.getElementById("form-error");
  box.textContent = message;
  box.hidden = false;
}

function renderStanding(box, standing) {
  /* The weekly analysis for this one pattern, shown a week early. Chip classes
     are the Plan page's, so a weak pattern reads the same red in both places. */
  if (!standing) return;
  const mastery = standing.score === null ? "unscored" : `mastery ${standing.score.toFixed(1)}/5`;
  if (!standing.enough_data) {
    const plural = standing.attempts === 1 ? "" : "s";
    box.append(el("p", { class: "hint", text:
      `${standing.pattern}: ${mastery} over only ${standing.attempts} attempt${plural} — not enough data to call it yet.` }));
    return;
  }
  box.append(
    el("p", {}, [
      el("span", {
        class: `chip ${standing.weak ? "weak-pattern" : "review"}`,
        text: standing.weak ? "weak pattern" : "on track",
      }),
      el("span", { text:
        ` ${standing.pattern}: ${mastery}, ${Math.round(standing.struggle_rate * 100)}% struggle rate` +
        ` over ${standing.attempts} attempts` }),
    ])
  );
}

function renderLogResult(data) {
  const box = document.getElementById("log-result");
  box.replaceChildren();
  box.hidden = false;

  box.append(el("h3", { text: `Logged (${data.number}) ${data.title} (${data.outcome})` }));
  box.append(el("p", { text: `Next review: ${data.next_due}` }));

  const e = data.enrichment;
  if (e.status === "skipped") {
    box.append(
      el("p", {}, [
        el("span", { class: "badge warn", text: "Enrichment pending" }),
        el("span", { text: ` ${e.reason} — run \`coach enrich\` to backfill.` }),
      ])
    );
    return;
  }

  box.append(
    el("p", {}, [
      el("span", { class: "badge pattern", text: e.pattern }),
      el("span", { text: ` ${e.key_trick}` }),
    ])
  );
  renderStanding(box, data.pattern_standing);
  if (e.secondary_patterns.length) {
    box.append(el("p", { class: "hint", text: `Also uses: ${e.secondary_patterns.join(", ")}` }));
  }
  if (e.off_pattern) {
    box.append(
      el("p", {}, [
        el("span", { class: "badge warn", text: "off-pattern" }),
        el("span", { text: ` the canonical approach is ${e.intended_pattern} — worth re-solving that way.` }),
      ])
    );
  }
  if (e.also_solvable_with?.length) {
    box.append(el("p", { class: "hint", text:
      `This problem can also be solved with: ${e.also_solvable_with.join(", ")}` }));
  }
  if (e.embedding_skipped) {
    box.append(el("p", { class: "hint", text: `Embedding skipped (${e.embedding_skipped})` }));
  } else if (e.neighbors.length) {
    box.append(el("p", { class: "hint", text: "Similar solved problems:" }));
    box.append(
      el("ul", {}, e.neighbors.map((n) =>
        el("li", { text: `(${n.number}) ${n.title} [${n.difficulty}] — ${n.pattern || "untagged"}` })
      ))
    );
  } else {
    box.append(el("p", { class: "hint", text: `No other solved problems tagged as ${e.pattern} yet.` }));
  }
}

async function submitLog(event) {
  event.preventDefault();
  const button = document.getElementById("submit");
  const errorBox = document.getElementById("form-error");
  errorBox.hidden = true;

  const number = Number(document.getElementById("number").value);
  const code = document.getElementById("code").value;
  const { valid, minutes, note } = optionalFields();
  if (!Number.isInteger(number) || number < 1) {
    showError("Enter the LeetCode problem number.");
    document.getElementById("number").focus();
    return;
  }
  if (!valid) {
    showError("Minutes must be a whole number — or leave it blank.");
    document.getElementById("minutes").focus();
    return;
  }
  if (!code.trim()) {
    showError("Paste the solution you wrote.");
    document.getElementById("code").focus();
    return;
  }

  button.disabled = true;
  button.textContent = "Logging…";
  try {
    const res = await fetch("/api/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ number, outcome: outcomeValue(), code, minutes, note }),
    });
    const data = await res.json();
    if (!res.ok) {
      showError(typeof data.detail === "string" ? data.detail : "That solve could not be logged.");
      return;
    }
    renderLogResult(data);
    document.getElementById("code").value = "";
    document.getElementById("minutes").value = "";
    document.getElementById("note").value = "";
    document.getElementById("log-result").focus();
    await refresh();
  } catch (err) {
    showError(`Could not reach the coach: ${err.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "Log this solve";
  }
}

/* ---------- wiring ---------- */

async function refresh() {
  const [stats, patterns] = await Promise.all([getJSON("/api/stats"), getJSON("/api/patterns")]);
  renderStats(stats);
  renderPatternTable(patterns.patterns);
}

function setup() {
  const logToggle = document.getElementById("log-toggle");
  const panel = document.getElementById("log-panel");
  logToggle.addEventListener("click", () => {
    const open = panel.hidden;
    panel.hidden = !open;
    logToggle.setAttribute("aria-expanded", String(open));
    if (open) document.getElementById("number").focus();
  });

  document.getElementById("log-form").addEventListener("submit", submitLog);
  document.getElementById("log-result").setAttribute("tabindex", "-1");

  refresh().catch((err) => {
    document.getElementById("hero-note").textContent = `Could not load stats: ${err.message}`;
  });
}

setup();
