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
function optionValues(id, rows, key) {
  const values = [...new Set(rows.map(row => row[key]))].sort();
  for (const value of values) {
    const option = node("option", label(value));
    option.value = value;
    $(id).append(option);
  }
}
function renderPortRegressions(report) {
  const status = $("port-regressions-status");
  if (!report?.available) {
    status.textContent = `Port regressions unavailable: ${report?.error || "no current observations"}`;
    return;
  }
  const counts = report.summary.python;
  const total = report.cases.length;
  status.textContent = `${total} project cases · ${counts.pass || 0} executable checks passed · ${counts.boundary_pass || 0} boundary checks passed · ${counts.known_defect || 0} known defects. Native branch differences: ${report.summary.native.branch_convention_difference || 0}. Overall: ${report.passed ? "passed" : "failed or incomplete"}. Legacy counts are unchanged.`;
  const info = node("div");
  info.append(details("Port suite provenance and runner errors", {provenance:report.provenance,errors:report.errors,runners:report.runners}));
  status.append(info);
  optionValues("port-group", report.cases, "group");
  function update() {
    const query = $("port-search").value.trim().toLowerCase();
    const rows = report.cases.filter(row => (!$("port-group").value || row.group === $("port-group").value) &&
      (!query || [row.id,row.group,row.student,row.teacher,row.reason].some(x => String(x).toLowerCase().includes(query))));
    $("port-regressions-list").replaceChildren(...rows.map(row => {
      const box = node("details", undefined, "case");
      const head = node("summary");
      head.append(node("span", `${row.id} · ${row.test}`), badge("Python",row.python_status),
                  badge("native vs desired",row.native_status), badge("parity",row.parity_status),
                  node("span",`${row.student} → ${row.teacher}`));
      box.append(head,node("p",row.reason));
      for (const [title,value] of [["Expected behavior and origin",{expected:row.expected,origin:row.origin,known_defect:row.known_defect,native_expected:row.native_expected,native_difference_reason:row.native_difference_reason}],
                                  ["Python observation",row.python],["Native observation",row.native],["Browser parity",row.parity]]) {
        box.append(details(title,value));
      }
      return box;
    }));
  }
  $("port-search").addEventListener("input",update);
  $("port-group").addEventListener("input",update);
  update();
}

fetch("port-regressions.json", {cache:"no-store"}).then(response => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).then(report => renderPortRegressions(report)).catch(error => {
  $("port-regressions-status").textContent = `Port regressions unavailable: ${error.message}`;
});
