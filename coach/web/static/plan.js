/* Daily Plan page: today's problems under three headings, then focus topics.
   el()/getJSON()/topicCard()/leetcodeLink() come from dom.js, loaded before this script. */

const plural = (n, noun) => `${n} ${noun}${n === 1 ? "" : "s"}`;

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
}

/* One problem, drawn like a row on Solutions: its name, difficulty and reasons, with the
   LeetCode link underneath. */
function planItem(item) {
  return el("li", {}, [
    el("div", { class: "problem-head" }, [
      el("span", { class: "title" }, [
        el("span", { class: "num", text: `(${item.number}) ` }),
        el("span", { text: item.title }),
      ]),
      el("span", { class: `diff ${item.difficulty}`, text: item.difficulty }),
      // One chip per reason, each styled by the rule that gave it.
      el("span", { class: "reasons" }, item.reasons.map((r) =>
        el("span", { class: `chip ${r.kind}`, text: r.text })
      )),
    ]),
    leetcodeLink(item.slug),
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
    // The status line only has something to say while loading or after a failure.
    document.getElementById("plan-meta").hidden = true;
  } catch (err) {
    // The status line heads the page, so a failure is the first thing on it.
    const meta = document.getElementById("plan-meta");
    meta.className = "error";
    meta.textContent = `Could not load the plan: ${err.message}`;
  }
}

load();
