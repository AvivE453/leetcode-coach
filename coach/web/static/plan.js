/* Daily Plan page: focus topics, then today's problems under three headings.
   el()/getJSON()/topicCard()/APPROACH_REASON come from dom.js, loaded before this script. */

const plural = (n, noun) => `${n} ${noun}${n === 1 ? "" : "s"}`;

/* One problem owing approach practice: the approaches that would complete it, its date,
   and why it is still owed. */
function correctionItem(c) {
  return el("li", {
    text: `(${c.number}) ${c.title} → ${c.accepted.join(" or ")} · due ${c.due} · ${APPROACH_REASON[c.reason]}`,
  });
}

function renderTopics(data) {
  const host = document.getElementById("topics");
  host.replaceChildren();
  const t = data.topics;
  // Thresholds come from the API so this copy tracks the Python constants.
  const th = data.thresholds || {};

  host.append(
    topicCard(
      "Stale patterns",
      `Nothing has gone stale (${th.stale_days}+ days untouched).`,
      t.stale,
      (p) => el("li", { text: p })
    )
  );
  // Due practice is its own heading below. Upcoming waits for its date, so a problem
  // just practised does not come straight back for being unresolved.
  host.append(
    topicCard(
      "Approach practice upcoming",
      "Nothing else is waiting on an accepted approach.",
      t.corrections_upcoming,
      correctionItem
    )
  );

  const { due, approach, weak } = data.sections;
  const parts = [`${plural(due.length + approach.length + weak.length, "problem")} today`];
  for (const [name, p] of Object.entries(data.curriculum)) parts.push(`${name} ${p.done}/${p.total}`);
  document.getElementById("plan-meta").textContent = parts.join(" · ");
}

function planItem(item) {
  return el("li", {}, [
    el("span", { class: "title" }, [
      el("span", { class: "num", text: `(${item.number}) ` }),
      el("a", {
        href: `https://leetcode.com/problems/${item.slug}/`,
        target: "_blank",
        rel: "noreferrer",
        text: item.title,
      }),
    ]),
    el("span", { class: `diff ${item.difficulty}`, text: item.difficulty }),
    // One chip per reason, each styled by the rule that gave it.
    el("span", { class: "reasons" }, item.reasons.map((r) =>
      el("span", { class: `chip ${r.kind}`, text: r.text })
    )),
  ]);
}

/* One heading: its problems, or a line saying why it has none. */
function renderSection(list, empty, items, emptyText) {
  list.replaceChildren(...items.map(planItem));
  empty.textContent = emptyText;
  empty.hidden = items.length > 0;
}

/* Reviews lead Due; curriculum progression only fills the slots they leave. */
function renderDue(data) {
  const items = data.sections.due;
  const reviews = items.filter((item) => item.reasons[0].kind === "review").length;
  let meta = "";
  if (data.reviews_owed > reviews) {
    meta = `Showing ${reviews} of ${data.reviews_owed} reviews due; the rest stay due and come first tomorrow.`;
  } else if (items.length > reviews) {
    meta = `${plural(reviews, "review")} due, topped up with curriculum progression.`;
  }
  document.getElementById("due-meta").textContent = meta;
  renderSection(
    document.getElementById("due-list"),
    document.getElementById("due-empty"),
    items,
    "No reviews due, and nothing left on the curriculum to add."
  );
}

function renderApproach(data) {
  const items = data.sections.approach;
  document.getElementById("approach-meta").textContent = data.practice_owed > items.length
    ? `Showing ${items.length} of ${data.practice_owed}; the rest stay due and come first tomorrow.`
    : "";
  renderSection(
    document.getElementById("approach-list"),
    document.getElementById("approach-empty"),
    items,
    "No problem owes approach practice today."
  );
}

function renderWeak(data) {
  const weak = data.topics.weak;
  const th = data.thresholds || {};
  document.getElementById("weak-meta").textContent = weak.length ? `Weak now: ${weak.join(", ")}` : "";
  renderSection(
    document.getElementById("weak-list"),
    document.getElementById("weak-empty"),
    data.sections.weak,
    weak.length
      ? "No unsolved curriculum problem carries a weak pattern's LeetCode tag."
      : `Nothing weak yet — a pattern needs ${th.weak_min_problems} distinct problems and a mastery score below ${th.weak_score} to count.`
  );
}

async function load() {
  try {
    const data = await getJSON("/api/plan");
    renderTopics(data);
    renderDue(data);
    renderApproach(data);
    renderWeak(data);
  } catch (err) {
    document.getElementById("topics").replaceChildren(
      el("p", { class: "error", text: `Could not load the plan: ${err.message}` })
    );
  }
}

load();
