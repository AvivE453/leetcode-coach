/* Shared by every page's own script. No build step, so this is a plain global
   loaded via <script> before the page script - see index.html/plan.html/
   solutions.html/weekly.html. */

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

/* A titled card that either lists items or shows a hint when there are none -
   the Daily Plan and Weekly Review pages' focus-topic and verdict cards. */
function topicCard(title, hint, items, render) {
  const card = el("div", { class: "card" }, [el("p", { class: "k", text: title })]);
  if (!items.length) {
    card.append(el("p", { class: "empty", text: hint }));
    return card;
  }
  card.append(el("ul", {}, items.map(render)));
  return card;
}

/* The link under a problem's name, on Solutions and the Daily Plan alike. */
function leetcodeLink(slug) {
  return el("p", { class: "problem-link" }, [
    el("a", {
      href: `https://leetcode.com/problems/${slug}/`,
      target: "_blank",
      rel: "noreferrer",
      text: "Open on leetcode.com",
    }),
  ]);
}

/* One badge per main pattern of a solve, space-separated. Main patterns are equal,
   so none is drawn as the lead - Home's log result and Solutions show the same. */
function patternBadges(patterns) {
  return patterns.flatMap((pattern, i) => [
    ...(i ? [" "] : []),
    el("span", { class: "badge pattern", text: pattern }),
  ]);
}

const DOTS = [".", "..", "...", ""];

/* Logging a solve and reviewing one are each a model call with nothing to show until
   it ends, so the button keeps counting to say the request is still alive. Returns the
   stop; the caller restores the label. */
function animateDots(button, word) {
  const dots = el("span", { class: "dots", "aria-hidden": "true" });
  button.replaceChildren(`${word} `, dots);
  let step = 0;
  const tick = () => { dots.textContent = DOTS[step++ % DOTS.length]; };
  tick();
  const timer = setInterval(tick, 400);
  return () => clearInterval(timer);
}

/* Why a problem still owes approach practice, keyed by the reason codes coach/corrections.py
   sends. Home and Solutions word the same codes, so they share this copy. */
const APPROACH_REASON = {
  "wrong-approach": "your last practice used none of the accepted approaches",
  failed: "your last practice day included a failed attempt",
  assisted: "your last practice day needed hints",
  "review-finding": "a review reported a problem with your last practice day",
};
