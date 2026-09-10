/* Daily Plan page: focus topics, then today's ranked problem list.
   el()/getJSON()/topicCard() come from dom.js, loaded before this script. */

function renderTopics(data) {
  const host = document.getElementById("topics");
  host.replaceChildren();
  const t = data.topics;
  // Thresholds come from the API so this copy tracks the Python constants.
  const th = data.thresholds || {};

  host.append(
    topicCard(
      "Weak patterns",
      `Nothing weak yet — a pattern needs ${th.weak_min_attempts} attempts and a mastery score below ${th.weak_score} to count.`,
      t.weak,
      (p) => el("li", { text: p })
    )
  );
  host.append(
    topicCard(
      "Stale patterns",
      `Nothing has gone stale (${th.stale_days}+ days untouched).`,
      t.stale,
      (p) => el("li", { text: p })
    )
  );
  host.append(
    topicCard(
      "Solved off-pattern",
      "Every solved problem has been done with its canonical approach.",
      t.off_pattern,
      (p) => el("li", { text: `(${p.number}) ${p.title} → ${p.intended_pattern}` })
    )
  );

  const parts = [`${data.items.length} problems today`, `${data.due_count} review${data.due_count === 1 ? "" : "s"} due today`];
  for (const [name, p] of Object.entries(data.curriculum)) parts.push(`${name} ${p.done}/${p.total}`);
  document.getElementById("plan-meta").textContent = parts.join(" · ");
}

function renderPlan(data) {
  const list = document.getElementById("plan-list");
  const empty = document.getElementById("plan-empty");
  list.replaceChildren();

  if (!data.items.length) {
    empty.hidden = false;
    empty.textContent = "Nothing to plan — the curriculum is finished and no reviews are due today.";
    return;
  }
  empty.hidden = true;

  for (const item of data.items) {
    list.append(
      el("li", {}, [
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
        el("span", { class: `chip ${item.kind}`, text: item.reason }),
      ])
    );
  }
}

async function load() {
  try {
    const data = await getJSON("/api/plan");
    renderTopics(data);
    renderPlan(data);
  } catch (err) {
    document.getElementById("topics").replaceChildren(
      el("p", { class: "error", text: `Could not load the plan: ${err.message}` })
    );
  }
}

load();
