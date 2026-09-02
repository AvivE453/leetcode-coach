/* Home page: progress numbers, the pattern bubble map, and the log form. */

const SVG_NS = "http://www.w3.org/2000/svg";
const W = 900;
const H = 520;

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

function svg(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== null) node.textContent = text;
  return node;
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return res.json();
}

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
  cards.append(statCard("Clean solves", `${rate}%`, `${clean} of ${s.attempts} attempts`));

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

/* ---------- bubble map ---------- */

function bubbleFill(value, max) {
  // Darker blue for rarely practiced patterns, brighter for the well-worn ones.
  const t = max > 1 ? (value - 1) / (max - 1) : 1;
  const from = [30, 58, 138];   // #1e3a8a
  const to = [59, 130, 246];    // #3b82f6
  const mix = from.map((c, i) => Math.round(c + (to[i] - c) * t));
  return `rgb(${mix.join(",")})`;
}

function labelLines(d, r) {
  /* Whole pattern name or nothing: a truncated "binary" or "dp" would read as a
     different pattern. One hyphen-separated word per line, sized to fit the
     widest one, with the count underneath when there is room. */
  const words = d.pattern.split("-");
  const longest = Math.max(...words.map((w) => w.length));
  const size = Math.min(
    (1.45 * r) / (0.58 * longest),      // widest word inside the circle
    (1.5 * r) / (1.15 * (words.length + 1)),  // words + the count line
    19
  );
  if (size < 9) return [];  // too small to read - the title and table still carry it

  const showCount = size >= 11;
  const rows = showCount ? words.length + 1 : words.length;
  let y = (-(rows - 1) * size * 1.15) / 2;

  const lines = words.map((word) => {
    const t = svg("text", { y, "font-size": size.toFixed(1) }, word);
    t.setAttribute("dominant-baseline", "middle");
    y += size * 1.15;
    return t;
  });
  if (showCount) {
    const t = svg("text", { class: "count", y, "font-size": (size * 0.85).toFixed(1) }, String(d.solved));
    t.setAttribute("dominant-baseline", "middle");
    lines.push(t);
  }
  return lines;
}

function renderBubbles(patterns) {
  const host = document.getElementById("bubbles");
  host.replaceChildren();

  if (!patterns.length) {
    host.append(el("p", {
      class: "loading",
      text: "No tagged solutions yet — log a solve (with an API key set) and patterns appear here.",
    }));
    return;
  }

  const root = d3.hierarchy({ children: patterns }).sum((d) => d.solved);
  d3.pack().size([W, H]).padding(8)(root);
  const leaves = root.leaves();
  const max = Math.max(...patterns.map((p) => p.solved));

  // Crop the viewBox to the packed circles so the card has no dead margin.
  const pad = 10;
  const minX = Math.min(...leaves.map((n) => n.x - n.r)) - pad;
  const minY = Math.min(...leaves.map((n) => n.y - n.r)) - pad;
  const maxX = Math.max(...leaves.map((n) => n.x + n.r)) + pad;
  const maxY = Math.max(...leaves.map((n) => n.y + n.r)) + pad;

  const chart = svg("svg", {
    viewBox: `${minX} ${minY} ${maxX - minX} ${maxY - minY}`,
    role: "list",
    "aria-label": `${patterns.length} practiced patterns, sized by problems solved`,
  });

  for (const node of leaves) {
    const d = node.data;
    const g = svg("g", {
      class: "bubble",
      role: "listitem",
      tabindex: "0",
      transform: `translate(${node.x},${node.y})`,
      "aria-label": `${d.pattern}: ${d.solved} problem${d.solved === 1 ? "" : "s"} solved`,
    });
    const circle = svg("circle", { r: node.r });
    circle.style.fill = bubbleFill(d.solved, max);
    g.append(circle);
    g.append(svg("title", {}, `${d.pattern} — ${d.solved} solved`));
    for (const line of labelLines(d, node.r)) g.append(line);
    chart.append(g);
  }
  host.append(chart);
}

function renderPatternTable(patterns) {
  const host = document.getElementById("pattern-table");
  host.replaceChildren();
  const rows = patterns.map((p) =>
    el("tr", {}, [el("td", { text: p.pattern }), el("td", { text: String(p.solved) })])
  );
  host.append(
    el("table", {}, [
      el("caption", { text: "The same data as the bubble map." }),
      el("thead", {}, [el("tr", {}, [el("th", { text: "Pattern" }), el("th", { text: "Problems solved" })])]),
      el("tbody", {}, rows),
    ])
  );
}

/* ---------- log form ---------- */

function outcomeValue() {
  return document.querySelector('input[name="outcome"]:checked').value;
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

  box.append(el("h3", { text: `Logged #${data.number} ${data.title} (${data.outcome})` }));
  box.append(el("p", { text: `Next review: ${data.next_due} · saved to ${data.solution_file}` }));

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
  if (e.embedding_skipped) {
    box.append(el("p", { class: "hint", text: `Embedding skipped (${e.embedding_skipped})` }));
  }
  if (e.neighbors.length) {
    box.append(el("p", { class: "hint", text: "Similar solved problems:" }));
    box.append(
      el("ul", {}, e.neighbors.map((n) =>
        el("li", { text: `#${n.number} ${n.title} [${n.difficulty}] — ${n.pattern || "untagged"}` })
      ))
    );
  }
}

async function submitLog(event) {
  event.preventDefault();
  const button = document.getElementById("submit");
  const errorBox = document.getElementById("form-error");
  errorBox.hidden = true;

  const number = Number(document.getElementById("number").value);
  const code = document.getElementById("code").value;
  if (!Number.isInteger(number) || number < 1) {
    showError("Enter the LeetCode problem number.");
    document.getElementById("number").focus();
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
      body: JSON.stringify({ number, outcome: outcomeValue(), code }),
    });
    const data = await res.json();
    if (!res.ok) {
      showError(typeof data.detail === "string" ? data.detail : "That solve could not be logged.");
      return;
    }
    renderLogResult(data);
    document.getElementById("code").value = "";
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
  renderBubbles(patterns.patterns);
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

  const viewToggle = document.getElementById("view-toggle");
  const table = document.getElementById("pattern-table");
  const bubbles = document.getElementById("bubbles");
  viewToggle.addEventListener("click", () => {
    const showTable = table.hidden;
    table.hidden = !showTable;
    bubbles.hidden = showTable;
    viewToggle.setAttribute("aria-expanded", String(showTable));
    viewToggle.textContent = showTable ? "Show as bubbles" : "Show as table";
  });

  document.getElementById("log-form").addEventListener("submit", submitLog);
  document.getElementById("log-result").setAttribute("tabindex", "-1");

  refresh().catch((err) => {
    document.getElementById("hero-note").textContent = `Could not load stats: ${err.message}`;
  });
}

setup();
