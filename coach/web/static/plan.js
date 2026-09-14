/* Daily Plan page: focus topics, then today's ranked problem list.
   el()/getJSON()/topicCard()/APPROACH_REASON come from dom.js, loaded before this script. */

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
      "Weak patterns",
      `Nothing weak yet — a pattern needs ${th.weak_min_problems} distinct problems and a mastery score below ${th.weak_score} to count.`,
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
  // Due practice is already in today's list below. Upcoming waits for its date, so a
  // problem just practised does not come straight back for being unresolved.
  host.append(
    topicCard(
      "Approach practice due",
      "No problem is owed an accepted approach today.",
      t.corrections_due,
      correctionItem
    )
  );
  host.append(
    topicCard(
      "Approach practice upcoming",
      "Nothing else is waiting on an accepted approach.",
      t.corrections_upcoming,
      correctionItem
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
        // One chip per reason, each styled by the rule that gave it.
        el("span", { class: "reasons" }, item.reasons.map((r) =>
          el("span", { class: `chip ${r.kind}`, text: r.text })
        )),
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
