/* Solutions page: every solved problem, expanding to the code you wrote. */

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

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return res.json();
}

function summaryLine(p) {
  const parts = [`${p.solves} solve${p.solves === 1 ? "" : "s"}`, `last ${p.last_solved} · ${p.last_outcome}`];
  if (p.pattern) parts.push(p.pattern);
  return parts.join(" · ");
}

const VERDICT_LABEL = {
  optimal: "optimal",
  acceptable: "correct, improvable",
  "needs-work": "needs work",
};

function renderReview(host, review) {
  host.replaceChildren();
  host.append(
    el("p", {}, [
      el("span", { class: `verdict ${review.verdict}`, text: VERDICT_LABEL[review.verdict] || review.verdict }),
      el("span", { class: "hint", text:
        ` your code: ${review.time_complexity} time / ${review.space_complexity} space` +
        ` · optimal: ${review.optimal_time_complexity}` }),
    ])
  );

  if (review.strengths.length) {
    host.append(el("p", { class: "review-head", text: "What went well" }));
    host.append(el("ul", { class: "good" }, review.strengths.map((s) => el("li", { text: s }))));
  }
  if (review.issues.length) {
    host.append(el("p", { class: "review-head", text: "What to improve" }));
    host.append(
      el("ul", { class: "bad" }, review.issues.map((i) =>
        el("li", {}, [
          el("span", { class: `chip ${i.category === "complexity" ? "re-solve" : "weak-pattern"}`, text: i.category }),
          el("span", { text: ` ${i.description}` }),
        ])
      ))
    );
  } else if (review.strengths.length) {
    host.append(el("p", { class: "hint", text: "No issues found." }));
  }
  if (review.better_approach) {
    host.append(el("p", { class: "review-head", text: "Better approach" }));
    host.append(el("p", { class: "hint", text: review.better_approach }));
  }
}

async function requestReview(number, solutionId, host, button) {
  button.disabled = true;
  button.textContent = "Reviewing…";
  try {
    const res = await fetch(`/api/solutions/${number}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ solution_id: solutionId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `returned ${res.status}`);
    if (data.status === "skipped") {
      button.disabled = false;
      button.textContent = "Review this solve";
      host.append(el("p", { class: "hint", text: `Review skipped: ${data.reason}` }));
      return;
    }
    renderReview(host, data.review);
  } catch (err) {
    button.disabled = false;
    button.textContent = "Review this solve";
    host.append(el("p", { class: "error", text: `Could not review: ${err.message}` }));
  }
}

function renderSolve(s, number) {
  const meta = [s.created_at, s.outcome];
  if (s.minutes) meta.push(`${s.minutes}m`);
  const block = el("div", { class: "solve" }, [
    el("p", { class: "solve-meta", text: meta.join(" · ") }),
  ]);
  if (s.pattern) {
    block.append(
      el("p", {}, [
        el("span", { class: "badge pattern", text: s.pattern }),
        el("span", { text: s.key_trick ? ` ${s.key_trick}` : "" }),
      ])
    );
  }
  if (s.time_complexity) {
    block.append(el("p", { class: "hint", text: `${s.time_complexity} time / ${s.space_complexity} space` }));
  }
  if (s.note) block.append(el("p", { class: "hint", text: `Note: ${s.note}` }));
  // textContent, never innerHTML - the code is whatever was pasted in.
  block.append(el("pre", {}, [el("code", { text: s.code })]));

  /* A stored review renders for free; asking for a new one costs an API call, so
     it is always an explicit click - never something opening the page pays for. */
  const reviewBox = el("div", { class: "review" });
  if (s.review) {
    renderReview(reviewBox, s.review);
  } else {
    const button = el("button", { class: "btn ghost", type: "button", text: "Review this solve" });
    reviewBox.append(
      el("p", { class: "hint", text: "No review yet — one API call, then it is saved for good." }),
      button
    );
    button.addEventListener("click", () => requestReview(number, s.id, reviewBox, button));
  }
  block.append(reviewBox);
  return block;
}

async function toggle(button, panel, number) {
  const open = panel.hidden;
  panel.hidden = !open;
  button.setAttribute("aria-expanded", String(open));
  if (!open || panel.dataset.loaded) return;

  try {
    const data = await getJSON(`/api/solutions/${number}`);
    panel.replaceChildren(...data.solves.map((s) => renderSolve(s, number)));
    panel.dataset.loaded = "yes";
  } catch (err) {
    panel.replaceChildren(el("p", { class: "error", text: `Could not load the code: ${err.message}` }));
  }
}

function renderProblem(p) {
  const panel = el("div", { class: "solve-panel", id: `solves-${p.number}`, hidden: "" });
  const button = el("button", {
    class: "solve-toggle",
    type: "button",
    "aria-expanded": "false",
    "aria-controls": `solves-${p.number}`,
  }, [
    el("span", { class: "title" }, [
      el("span", { class: "num", text: `#${p.number} ` }),
      el("span", { text: p.title }),
    ]),
    el("span", { class: `diff ${p.difficulty}`, text: p.difficulty }),
    el("span", { class: "hint", text: summaryLine(p) }),
  ]);
  button.addEventListener("click", () => toggle(button, panel, p.number));

  return el("li", {}, [
    button,
    el("p", { class: "solve-link" }, [
      el("a", {
        href: `https://leetcode.com/problems/${p.slug}/`,
        target: "_blank",
        rel: "noreferrer",
        text: "Open on leetcode.com",
      }),
    ]),
    panel,
  ]);
}

async function load() {
  const list = document.getElementById("solutions-list");
  const empty = document.getElementById("solutions-empty");
  try {
    const { problems } = await getJSON("/api/solutions");
    if (!problems.length) {
      empty.textContent = "Nothing logged yet — solve something and log it from the home page.";
      return;
    }
    empty.hidden = true;
    list.replaceChildren(...problems.map(renderProblem));
    const solves = problems.reduce((n, p) => n + p.solves, 0);
    document.getElementById("solutions-meta").textContent =
      `${problems.length} problem${problems.length === 1 ? "" : "s"} · ${solves} solve${solves === 1 ? "" : "s"}`;
  } catch (err) {
    empty.className = "error";
    empty.textContent = `Could not load your solutions: ${err.message}`;
  }
}

load();
