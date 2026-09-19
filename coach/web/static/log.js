/* Log a solve page: the form, and what the server made of the solve.
   el()/patternBadges()/animateDots()/APPROACH_REASON come from dom.js, loaded before this script. */

function outcomeValue() {
  return document.querySelector('input[name="outcome"]:checked').value;
}

/* The number fields are plain text inputs - a number input's spinner, scroll wheel and
   arrow keys changed the value by accident - so the browser no longer rejects non-digits. */
const WHOLE_NUMBER = /^\d+$/;

/* Minutes and note are optional: blank means "not recorded" and is sent as null. */
function optionalFields() {
  const raw = document.getElementById("minutes").value.trim();
  const minutes = raw === "" ? null : Number(raw);
  const valid = raw === "" || WHOLE_NUMBER.test(raw);
  const note = document.getElementById("note").value.trim() || null;
  return { valid, minutes, note };
}

function showError(message) {
  const box = document.getElementById("form-error");
  box.textContent = message;
  box.hidden = false;
}

function renderStanding(box, standing) {
  /* The weekly analysis for one of the solve's main patterns, shown a week early. Chip
     classes are the Plan page's, so a weak pattern reads the same red in both places. */
  const mastery = `mastery ${standing.score.toFixed(1)}/5`;
  const count = (n, noun) => `${n} ${noun}${n === 1 ? "" : "s"}`;
  const practice = `${count(standing.attempts, "solution")} submitted across`;
  if (!standing.enough_data) {
    box.append(el("p", { class: "hint", text:
      `${standing.pattern}: ${mastery} over ${practice} only ${count(standing.solved, "problem")}` +
      ` — not enough data to call it yet.` }));
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
        ` over ${practice} ${count(standing.solved, "problem")}` }),
    ])
  );
}

/* What this solve means for approach practice. The server judges it after tagging, so the
   solve's own tags count - and with tagging skipped, an earlier solve can still owe it. */
function approachPracticeNote(data) {
  const { practice, enrichment: e } = data;
  const owed = practice.correction;
  if (practice.completed) {
    return el("p", { text:
      `Accepted approach completed successfully. Your next review is ${practice.review_due}.` });
  }
  if (!owed) {
    if (!e.off_pattern) return null;
    return el("p", {}, [
      el("span", { class: "badge warn", text: "off-pattern" }),
      el("span", { text: " but you have already solved it with an accepted approach, so no approach practice is owed." }),
    ]);
  }
  if (e.status === "skipped") {
    return el("p", { class: "hint", text:
      `Approach practice is still owed, due ${owed.due}: ${APPROACH_REASON[owed.reason]}.` });
  }
  if (e.off_pattern) {
    return el("p", {}, [
      el("span", { class: "badge warn", text: "off-pattern" }),
      el("span", { text:
        ` none of the accepted approaches (${owed.accepted.join(" or ")}) — approach practice is due ${owed.due}.` }),
    ]);
  }
  return el("p", { text:
    `This attempt used an accepted approach, but ${APPROACH_REASON[owed.reason]}. ` +
    `Approach practice is due ${owed.due}.` });
}

function renderLogResult(data) {
  const box = document.getElementById("log-result");
  box.replaceChildren();
  box.hidden = false;

  box.append(el("div", { class: "result-head" }, [
    el("h3", { text: `Logged (${data.number}) ${data.title} (${data.outcome})` }),
    el("a", { class: "btn ghost", href: `/solutions?number=${data.number}`, text: "Go to review" }),
  ]));
  box.append(el("p", { text: `Next review: ${data.practice.review_due}` }));
  if (!data.counted_as_review) {
    box.append(el("p", { class: "hint", text:
      "Not counted as a review, so that date did not move: solved before it was due, or again on a day already counted." }));
  }
  const note = approachPracticeNote(data);
  if (note) box.append(note);

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
      ...patternBadges(e.main_patterns),
      el("span", { text: ` ${e.key_trick}` }),
    ])
  );
  for (const standing of data.pattern_standings) renderStanding(box, standing);
  if (e.secondary_patterns.length) {
    box.append(el("p", { class: "hint", text: `Also uses: ${e.secondary_patterns.join(", ")}` }));
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
        el("li", { text: `(${n.number}) ${n.title} [${n.difficulty}] — ${n.main_patterns.join(", ") || "untagged"}` })
      ))
    );
  } else {
    box.append(el("p", { class: "hint", text: `No other solved problems tagged as ${e.main_patterns.join(" or ")} yet.` }));
  }
}

async function submitLog(event) {
  event.preventDefault();
  const button = document.getElementById("submit");
  const errorBox = document.getElementById("form-error");
  errorBox.hidden = true;

  const rawNumber = document.getElementById("number").value.trim();
  const number = Number(rawNumber);
  const code = document.getElementById("code").value;
  const { valid, minutes, note } = optionalFields();
  if (!WHOLE_NUMBER.test(rawNumber) || number < 1) {
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
  const stopDots = animateDots(button, "Logging");
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
  } catch (err) {
    showError(`Could not reach the coach: ${err.message}`);
  } finally {
    stopDots();
    button.disabled = false;
    button.textContent = "Log this solve";
  }
}

function setup() {
  document.getElementById("log-form").addEventListener("submit", submitLog);
  document.getElementById("log-result").setAttribute("tabindex", "-1");

  // The Daily Plan links here as /log?number=N; with the number filled, the solution is next.
  const linked = Number(new URLSearchParams(location.search).get("number"));
  if (Number.isInteger(linked) && linked > 0) {
    document.getElementById("number").value = String(linked);
    document.getElementById("code").focus();
  } else {
    document.getElementById("number").focus();
  }
}

setup();
