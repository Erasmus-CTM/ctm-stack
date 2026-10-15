"use strict";

const $ = id => document.getElementById(id);
const node = (tag, text, className) => {
  const el = document.createElement(tag);
  if (text !== undefined && text !== null) el.textContent = String(text);
  if (className) el.className = className;
  return el;
};
const pretty = value => JSON.stringify(value === undefined ? null : value, null, 2);
const label = text => String(text).replaceAll("_", " ");
function safeLink(url, text) {
  if (!url || !/^https:\/\/github\.com\//.test(url)) return node("span", text);
  const a = node("a", text);
  a.href = url;
  a.rel = "noopener noreferrer";
  return a;
}
function badge(axis, status) {
  const el = node("span", `${axis}: ${label(status)}`, "badge");
  el.dataset.status = status;
  return el;
}
function details(title, content) {
  const box = node("details");
  box.append(node("summary", title), node("pre", pretty(content)));
  return box;
}
function summary(report) {
  const p = report.provenance;
  const provenance = $("report-provenance");
  const fixtureLink = $("fixture-link");
  if (/^[0-9a-f]{40}$/.test(p.code_sha || "")) {
    fixtureLink.replaceChildren(safeLink(`https://github.com/Erasmus-CTM/stack-sympy/blob/${p.code_sha}/tests/native_compliance/fixtures.json`, "Fixture at report commit"));
  } else {
    fixtureLink.textContent = "Fixture commit link unavailable";
  }
  provenance.append(node("strong", `Generated ${report.generated_at} · ${report.cases.length} imported static rows`));
  const metadata = node("p");
  metadata.append(`Code ${p.code_sha || "unavailable"} · Fixture SHA-256 ${p.fixture_sha256} · Upstream ${p.fixture_upstream?.commit || "unavailable"} · Python ${p.python_version || "unavailable"}. `);
  if (p.run_url) metadata.append(safeLink(p.run_url, "CI run and artifacts"));
  provenance.append(metadata, details("Fixture inventory and provenance", {inventory:p.fixture_inventory,upstream:p.fixture_upstream,scope:report.scope}));
  const eligible = report.results.parity.summary;
  if (eligible) provenance.append(node("p", `Browser grading parity: ${eligible.eligible_matched ?? "unavailable"} matching eligible executions of ${eligible.eligible ?? "unavailable"}; whole-inventory classification includes unsupported cases. Native direct-CAS observations: ${report.results.native.summary?.ok ?? "unavailable"} of ${report.cases.length} imported rows. Ordinary feedback notes are not compared; authored controlled-error notes are checked separately.`));
  const verdicts = node("p", undefined, "report-verdicts");
  for (const [key,title] of [["python","Desired outcome"],["compatibility","Native compatibility"],["parity","Browser parity"]]) {
    const result = report.results[key];
    verdicts.append(badge(title, !result.available ? "unavailable" : result.passed === true ? "pass" : "failed"), " ");
  }
  provenance.append(verdicts);

  for (const [axis,title] of [["desired","Python vs desired result"],["native","Reviewed native comparison"],["native_mark","Python vs native final mark"],["native_applicability","Python vs native CAS applicability"],["native_desired","Native vs desired result"],["parity","Pyodide vs CPython"]]) {
    const section = node("section");
    section.append(node("h3", title));
    const dl = node("dl");
    for (const [status,count] of Object.entries(report.summary[axis]).sort()) {
      dl.append(node("dt", label(status)), node("dd", count));
    }
    section.append(dl);
    $("report-summary").append(section);
  }
  for (const [engine,result] of Object.entries(report.results)) {
    const state = !result.available ? "unavailable" : result.error ? "reported error" :
                  result.passed === false ? "check failed" : "result available";
    $("report-runners").append(details(`${engine}: ${state}`, result));
  }
}
function optionValues(id, rows, key) {
  const values = [...new Set(rows.map(row => row[key]))].sort();
  for (const value of values) {
    const option = node("option", label(value));
    option.value = value;
    $(id).append(option);
  }
}
function caseElement(row) {
  const box = node("details", undefined, "case");
  const head = node("summary");
  head.append(node("span", `#${row.ordinal} · ${row.test}`, "case-test"),
              badge("desired", row.desired_status), badge("native", row.native_status),
              badge("mark", row.native_mark_status), badge("CAS applicable", row.native_applicability_status),
              badge("native vs desired", row.native_desired_status),
              badge("parity", row.parity_status), node("span", `${row.student} → ${row.teacher}`));
  box.append(head);
  const body = node("div", undefined, "case-detail");
  for (const [title,value] of [
    ["Raw upstream row", {student:row.student,teacher:row.teacher,options:row.options,expected_score:row.expected_score,answer_note:row.answer_note,notes:row.notes,extra_fields:row.extra_fields}],
    ["Python observation", row.python], ["Native STACK observation", row.native],
    ["Native compatibility verdict", {verdict:row.compatibility,raw_boolean_comparison:row.native_boolean_status}],
    ["Browser parity", row.parity], ["Answer-note comparison", row.answer_note_status]]) {
    const section = node("section");
    section.append(node("h4", title), node("pre", pretty(value)));
    body.append(section);
  }
  const provenance = node("p");
  provenance.append(`Case ID: ${row.id} · Upstream line ${row.source_line ?? "unknown"} · `,
                    safeLink(row.source_url, "View upstream source"));
  box.append(body, provenance);
  return box;
}
fetch("report.json", {cache:"no-store"}).then(response => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).then(report => {
  $("report-loading").hidden = true;
  $("report-root").hidden = false;
  summary(report);
  optionValues("test-filter", report.cases, "test");
  for (const axis of ["desired","native","native_mark","native_applicability","native_desired","parity"]) optionValues(`${axis}-filter`, report.cases, `${axis}_status`);
  let visible = 80;
  function update() {
    const query = $("case-search").value.trim().toLowerCase();
    const matches = report.cases.filter(row =>
      (!$("test-filter").value || row.test === $("test-filter").value) &&
      ["desired","native","native_mark","native_applicability","native_desired","parity"].every(axis => !$(axis+"-filter").value || row[axis+"_status"] === $(axis+"-filter").value) &&
      (!query || [row.id,row.test,row.student,row.teacher,row.options,row.notes,row.answer_note,pretty(row.extra_fields)].some(value => String(value ?? "").toLowerCase().includes(query))));
    $("case-count").textContent = `${matches.length} matching rows; showing ${Math.min(visible,matches.length)}`;
    $("case-list").replaceChildren(...matches.slice(0,visible).map(caseElement));
    $("show-more").hidden = matches.length <= visible;
  }
  for (const id of ["case-search","test-filter","desired-filter","native-filter","native_mark-filter","native_applicability-filter","native_desired-filter","parity-filter"]) {
    $(id).addEventListener("input", () => { visible = 80; update(); });
  }
  $("show-more").addEventListener("click", () => { visible += 80; update(); });
  update();
}).catch(error => {
  $("report-loading").textContent = `Report data unavailable: ${error.message}`;
});
