/* Solutions page: every solved problem, expanding to the code you wrote.
   el()/getJSON() come from dom.js, loaded before this script. */

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

/* The one place a review box is drawn, with or without a review in it. A stored
   review renders for free; asking for one - the first or a replacement - costs
   an API call, so it is always an explicit click, never something opening the
   page pays for. */
function fillReviewBox(box, number, solutionId, review) {
  box.replaceChildren();
  if (review) {
    renderReview(box, review);
    box.append(
      el("p", { class: "hint", text: "Re-running asks the model again — one API call, and the new review replaces this one." }),
      reviewButton(box, number, solutionId, "Re-run review", true)
    );
  } else {
    box.append(
      el("p", { class: "hint", text: "No review yet — one API call, then it is saved for good." }),
      reviewButton(box, number, solutionId, "Review this solve", false)
    );
  }
}

function reviewButton(box, number, solutionId, label, refresh) {
  const button = el("button", { class: "btn ghost", type: "button", text: label });
  button.addEventListener("click", () => requestReview(box, number, solutionId, button, refresh));
  return button;
}

async function requestReview(box, number, solutionId, button, refresh) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Reviewing…";
  try {
    const res = await fetch(`/api/solutions/${number}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ solution_id: solutionId, refresh }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `returned ${res.status}`);
    if (data.status === "skipped") {
      box.append(el("p", { class: "hint", text: `Review skipped: ${data.reason}` }));
      return;
    }
    fillReviewBox(box, number, solutionId, data.review);
  } catch (err) {
    box.append(el("p", { class: "error", text: `Could not review: ${err.message}` }));
  } finally {
    // After a success the box was redrawn and this button is already detached.
    button.disabled = false;
    button.textContent = label;
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
  /* Computed server-side on every load, not frozen with the review: if the
     problem's canonical set widens later, an old solve's note widens too. */
  if (s.also_solvable_with?.length) {
    block.append(el("p", { class: "hint", text:
      `Can also be solved with: ${s.also_solvable_with.join(", ")}` }));
  }
  if (s.time_complexity) {
    block.append(el("p", { class: "hint", text: `${s.time_complexity} time / ${s.space_complexity} space` }));
  }
  if (s.note) block.append(el("p", { class: "hint", text: `Note: ${s.note}` }));
  // textContent, never innerHTML - the code is whatever was pasted in.
  block.append(el("pre", {}, [el("code", { text: s.code })]));

  const reviewBox = el("div", { class: "review" });
  fillReviewBox(reviewBox, number, s.id, s.review);
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
      el("span", { class: "num", text: `(${p.number}) ` }),
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

/* The server owns both rules - the last-N default and what a query matches
   (service.solutions_listing) - so this only draws what it is sent. */
function renderListing(data) {
  const empty = document.getElementById("solutions-empty");
  const meta = document.getElementById("solutions-meta");
  const { problems, query, total_problems: total, total_solves: solves } = data;

  document.getElementById("solutions-list").replaceChildren(...problems.map(renderProblem));
  empty.className = "loading";
  empty.hidden = problems.length > 0;

  if (!total) {
    empty.textContent = "Nothing logged yet — solve something and log it from the home page.";
    meta.textContent = "";
    return;
  }
  if (!problems.length) empty.textContent = `No solved problem matches "${query}".`;

  if (query) {
    meta.textContent = `${problems.length} match${problems.length === 1 ? "" : "es"} for "${query}"`;
  } else {
    // Totals count everything, so a capped list can say how much it left out.
    const of = problems.length < total ? `${problems.length} most recent of ` : "";
    meta.textContent = `${of}${total} problem${total === 1 ? "" : "s"} · ${solves} solve${solves === 1 ? "" : "s"}`;
  }
}

/* Each keystroke can start a request, and replies need not arrive in order: a
   slow one for "1" must not overwrite a fast one for "12". Only the newest draws. */
let latest = 0;

async function load(query = "") {
  const seq = ++latest;
  try {
    const data = await getJSON(`/api/solutions?q=${encodeURIComponent(query)}`);
    if (seq === latest) renderListing(data);
  } catch (err) {
    if (seq !== latest) return;
    const empty = document.getElementById("solutions-empty");
    document.getElementById("solutions-list").replaceChildren();
    empty.hidden = false;
    empty.className = "error";
    empty.textContent = `Could not load your solutions: ${err.message}`;
  }
}

let typing;
document.getElementById("solutions-search").addEventListener("input", (e) => {
  clearTimeout(typing);
  typing = setTimeout(() => load(e.target.value), 150);
});

load();
