/* Weekly Plan page: focus topics, then the ranked problem list. */

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

function topicCard(title, hint, items, render) {
  const card = el("div", { class: "card" }, [
    el("p", { class: "k", text: title }),
  ]);
  if (!items.length) {
    card.append(el("p", { class: "empty", text: hint }));
    return card;
  }
  card.append(el("ul", {}, items.map(render)));
  return card;
}

function renderTopics(data) {
  const host = document.getElementById("topics");
  host.replaceChildren();
  const t = data.topics;

  host.append(
    topicCard(
      "Weak patterns",
      "Nothing weak yet — a pattern needs five attempts and a mastery score below 2.5 to count.",
      t.weak,
      (p) => el("li", { text: p })
    )
  );
  host.append(
    topicCard(
      "Stale patterns",
      "Nothing has gone stale (30+ days untouched).",
      t.stale,
      (p) => el("li", { text: p })
    )
  );
  host.append(
    topicCard(
      "Solved off-pattern",
      "Every solved problem has been done with its canonical approach.",
      t.off_pattern,
      (p) => el("li", { text: `#${p.number} ${p.title} → ${p.intended_pattern}` })
    )
  );

  const parts = [`${data.items.length} problems planned`, `${data.due_count} review${data.due_count === 1 ? "" : "s"} due`];
  for (const [name, p] of Object.entries(data.curriculum)) parts.push(`${name} ${p.done}/${p.total}`);
  document.getElementById("plan-meta").textContent = parts.join(" · ");
}

function renderPlan(data) {
  const list = document.getElementById("plan-list");
  const empty = document.getElementById("plan-empty");
  list.replaceChildren();

  if (!data.items.length) {
    empty.hidden = false;
    empty.textContent = "Nothing to plan — the curriculum is finished and no reviews are due.";
    return;
  }
  empty.hidden = true;

  for (const item of data.items) {
    list.append(
      el("li", {}, [
        el("span", { class: "title" }, [
          el("span", { class: "num", text: `#${item.number} ` }),
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
    const res = await fetch("/api/plan");
    if (!res.ok) throw new Error(`the coach returned ${res.status}`);
    const data = await res.json();
    renderTopics(data);
    renderPlan(data);
  } catch (err) {
    document.getElementById("topics").replaceChildren(
      el("p", { class: "error", text: `Could not load the plan: ${err.message}` })
    );
  }
}

load();
