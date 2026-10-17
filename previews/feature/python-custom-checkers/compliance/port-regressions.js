'use strict';
const U=ReportUI, {$,node}=U;
const comparisons={
  port_result:{name:'Port vs expected',help:'Does the port meet the expected behavior of each case?',get:r=>r.python_status},
  stack_result:{name:'STACK vs expected',help:'Does STACK meet the expected behavior, or use a documented different convention?',get:r=>r.native_status},
  browser_result:{name:'Browser vs Python',help:'Does the browser reproduce the port’s result or input handling?',get:U.parityStatus},
};
function caseElement(row) {
  const box=node('details',undefined,'case');const head=node('summary');
  const badges=node('span',undefined,'case-badges');for(const spec of Object.values(comparisons))badges.append(U.badge(spec.name,spec.get(row)));
  head.append(node('span',`${U.caseTitle(row)} · ${row.test}`,'case-test'),badges,U.expressions(row.student,row.teacher));box.append(head);
  // Known differences are explained without requiring the reader to infer a
  // conclusion from the color, a raw status name, or a JSON object.
  if(row.native_status==='branch_convention_difference')head.append(node('p','Known convention difference: the port rejects this equality; STACK accepts it. Open for the reason.','case-inline-note'));
  const body=node('div',undefined,'case-body');
  body.append(node('p',U.conclusion(row,true),'case-conclusion'));
  body.append(node('p',U.testHelp(row.test),'test-help'),U.outcomes(row.expected,row.python,row.native,row.parity));
  body.append(node('p',row.reason,'case-explanation'));
  if(row.known_defect?.reason)body.append(node('p',row.known_defect.reason));
  if(row.native_difference_reason)body.append(node('p',row.native_difference_reason));
  const raw=node('details',undefined,'technical-details');raw.append(node('summary','Raw observations and source'));
  raw.append(U.details('Expected behavior and origin',{id:row.id,group:row.group,expected:row.expected,origin:row.origin,known_defect:row.known_defect,native_expected:row.native_expected}),
    U.details('Port observation',row.python),U.details('STACK observation',row.native),U.details('Browser observation',row.parity));
  body.append(raw);box.append(body);return box;
}
function initialize(report) {
  const status=$('port-regressions-status');
  if(!report?.available){status.textContent=`Saved regression results unavailable: ${report?.error || 'no current observations'}`;return;}
  const counts=report.summary.python;
  status.className='report-overview';
  status.append(node('strong',`${report.cases.length} project cases · ${counts.known_defect||0} known port issue${counts.known_defect===1?'':'s'}`));
  // Remove the loading text before adding the compact overview.
  status.firstChild?.nodeType===Node.TEXT_NODE && status.firstChild.remove();
  status.append(node('p',`${counts.pass||0} checks meet their expected result; ${counts.boundary_pass||0} boundary checks verify invalid or unsupported input handling. ${report.summary.native.branch_convention_difference||0} root-convention difference is documented.`));
  if(report.passed)status.append(node('p','No unexpected changes in this saved run. Known issues and differences are still shown.'));
  else status.append(node('p','Some saved checks failed or are incomplete. Open the cases and runner details for the reason.'));
  const controls={};
  function update(){
    const query=$('port-search').value.trim().toLowerCase();
    const rows=report.cases.filter(r=>(!$('port-group').value || r.group===$('port-group').value) &&
      Object.entries(comparisons).every(([key,spec])=>!controls[key].value || spec.get(r)===controls[key].value) &&
      (!query || [r.id,r.group,r.student,r.teacher,r.reason,r.native_difference_reason].some(x=>String(x??'').toLowerCase().includes(query))));
    $('port-case-count').textContent=`${rows.length} of ${report.cases.length} project cases`;
    $('port-regressions-list').replaceChildren(...rows.map(caseElement));
  }
  for(const [key,spec] of Object.entries(comparisons))controls[key]=U.comparison(key,spec,report.cases,$('port-summary'),$('port-filters'),update);
  for(const group of [...new Set(report.cases.map(r=>r.group))].sort()){const option=node('option',group);option.value=group;$('port-group').append(option);}
  $('port-search').addEventListener('input',update);$('port-group').addEventListener('change',update);
  $('clear-filters').addEventListener('click',()=>{for(const el of Object.values(controls))el.value='';$('port-search').value='';$('port-group').value='';update();});
  $('port-provenance').append(U.details('Saved run, provenance, and runner details',{provenance:report.provenance,errors:report.errors,runners:report.runners}));
  update();
}
fetch('port-regressions.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json();}).then(initialize).catch(error=>{$('port-regressions-status').textContent=`Saved results unavailable: ${error.message}`;});
