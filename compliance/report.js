'use strict';
const U=ReportUI, {$,node,specs}=U;
const primary=['desired','native','parity'];
const extra=['native_mark','native_applicability','native_desired'];
const controls={};
let report, visible=60;
function update() {
  const query=$('case-search').value.trim().toLowerCase();
  const rows=report.cases.filter(r => (!$('test-filter').value || r.test===$('test-filter').value) &&
    [...primary,...extra].every(k => !controls[k].value || specs[k].get(r)===controls[k].value) &&
    (!query || [r.ordinal,r.id,r.test,r.student,r.teacher,r.options,r.notes,r.answer_note].some(x=>String(x??'').toLowerCase().includes(query))));
  $('case-count').textContent=`${rows.length.toLocaleString()} of ${report.cases.length.toLocaleString()} source cases · showing ${Math.min(visible,rows.length)}`;
  $('case-list').replaceChildren(...rows.slice(0,visible).map(caseElement));
  $('show-more').hidden=rows.length<=visible;
}
function caseElement(row) {
  const box=node('details',undefined,'case');const head=node('summary');
  const title=node('span',`#${row.ordinal} · ${row.test}`,'case-test');
  const badges=node('span',undefined,'case-badges');
  for(const key of primary)badges.append(U.badge(specs[key].name,specs[key].get(row)));
  head.append(title,badges,U.expressions(row.student,row.teacher));box.append(head);
  const body=node('div',undefined,'case-body');
  body.append(node('p',U.conclusion(row),'case-conclusion'),node('p',U.testHelp(row.test),'test-help'));
  body.append(U.outcomes(row.python?.desired,row.python,row.native,row.parity));
  const reason=row.python?.reason || row.compatibility?.reason;
  if(reason)body.append(node('p',reason,'case-explanation'));
  if(row.discussion) {
    const discussion=node('section',undefined,'case-discussion');
    if(!reason)discussion.append(node('p',row.discussion.explanation));
    discussion.append(node('p',row.discussion.evidence==='observed_behavior'
      ? 'Evidence: observed fixture/native behavior and implementation; no case-specific upstream rationale located.'
      : 'Evidence: upstream documentation gives relevant context; it does not fully specify this case’s domain.'));
    if(row.discussion.question)discussion.append(node('p',`Question for STACK: ${row.discussion.question}`));
    const sources=node('ul');for(const source of row.discussion.sources){const li=node('li');li.append(U.link(source.url,source.label));sources.append(li);}discussion.append(sources);body.append(discussion);
  }
  if(row.test==='EqualComAss' && /AlgEquiv-true/.test(row.native?.answer_note || ''))body.append(node('p','STACK proves the values equivalent, but rejects their written forms under EqualComAss.'));
  const comparisons=node('div',undefined,'additional-badges');for(const key of extra)comparisons.append(U.badge(specs[key].name,specs[key].get(row)));body.append(comparisons);
  const raw=node('details',undefined,'technical-details');raw.append(node('summary','Raw observations and source'));
  raw.append(U.details('Original test case',{student:row.student,teacher:row.teacher,options:row.options,expected_score:row.expected_score,answer_note:row.answer_note,notes:row.notes,extra_fields:row.extra_fields}),
    U.details('Port observation',row.python),U.details('STACK observation',row.native),U.details('Reviewed comparison',row.compatibility),U.details('Browser observation',row.parity),U.details('Answer-note handling',row.answer_note_status));
  const source=node('p');source.append(`Case ID: ${row.id} · `,U.link(row.source_url,`Upstream source, line ${row.source_line ?? 'unknown'}`));raw.append(source);body.append(raw);box.append(body);return box;
}
function initialize(data) {
  report=data;$('report-loading').hidden=true;$('report-root').hidden=false;
  const issues=report.summary.desired.known_defect||0;
  const overview=$('report-overview');
  const domain=report.cases.filter(r=>r.desired_status==='known_defect' && r.discussion?.category==='domain_review').length;
  const proofs=report.cases.filter(r=>r.desired_status==='known_defect' && r.discussion?.category==='proof_limitation').length;
  overview.append(node('strong',`${report.cases.length.toLocaleString()} source cases · ${issues} recorded differences or limitations`));
  if(domain || proofs)overview.append(node('p',`${domain} domain or branch differences need agreed assumptions with STACK; ${proofs} identities still lack a certified proof. Open each case for the explanation, counterexample where applicable, sources, and question for discussion.`));
  const outside=report.cases.filter(r=>r.desired_status==='out_of_contract');
  const missingTests=outside.filter(r=>specs.desired.get(r)==='port_test_unsupported').length;
  const missingInputs=outside.filter(r=>specs.desired.get(r)==='port_not_supported').length;
  const inputErrors=outside.filter(r=>specs.desired.get(r)==='port_input_error').length;
  overview.append(node('p',`Port coverage gaps: ${missingTests.toLocaleString()} cases use answer tests not yet implemented; ${missingInputs.toLocaleString()} use inputs or features not yet supported. A further ${inputErrors} cases produced input/reference errors instead of a comparable mark.`));
  if(report.results.python.passed && report.results.compatibility.passed)overview.append(node('p','The saved checks found no unexpected port results or unreviewed port/STACK disagreements among compared cases. Known issues remain listed below.'));
  const change=()=>{visible=60;update();};
  for(const key of primary)controls[key]=U.comparison(key,specs[key],report.cases,$('report-summary'),$('comparison-filters'),change);
  for(const key of extra)controls[key]=U.comparison(key,specs[key],report.cases,$('extra-summary'),$('extra-filters'),change);
  for(const test of [...new Set(report.cases.map(r=>r.test))].sort()){const option=node('option',test);option.value=test;$('test-filter').append(option);}
  $('case-search').addEventListener('input',change);$('test-filter').addEventListener('change',change);
  $('show-more').addEventListener('click',()=>{visible+=60;update();});
  $('clear-filters').addEventListener('click',()=>{for(const el of Object.values(controls))el.value='';$('case-search').value='';$('test-filter').value='';change();});
  const p=report.provenance;
  $('report-provenance').append(U.details('Saved run and provenance',{generated_at:report.generated_at,...p,scope:report.scope}));
  if(p.run_url)$('report-provenance').append(U.link(p.run_url,'Original run and artifacts'));
  for(const [name,result] of Object.entries(report.results))$('report-runners').append(U.details(`${name}: saved runner details`,result));
  if(/^[0-9a-f]{40}$/.test(p.code_sha || ''))$('fixture-link').append(U.link(`https://github.com/Erasmus-CTM/ctm-checkers/blob/${p.code_sha}/tests/stack/native_compliance/fixtures.json`,'Original test case at this run'));
  update();
}
fetch('report.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json();}).then(initialize).catch(error=>{
  $('report-loading').hidden=false;$('report-loading').textContent=`Saved results unavailable: ${error.message}`;
});
