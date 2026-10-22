/* Shared presentation vocabulary. This file only reads saved observations. */
'use strict';
globalThis.ReportUI = (() => {
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined && text !== null) el.textContent = String(text);
    if (className) el.className = className;
    return el;
  };
  const $ = id => document.getElementById(id);
  const pretty = value => JSON.stringify(value ?? null, null, 2);
  const states = {
    pass: ['As expected', 'good', 'The port produced the expected answer-test result.'],
    boundary_pass: ['Expected input handling', 'neutral', 'The case was correctly refused or reported as invalid; it was not a successful mathematical comparison.'],
    known_defect: ['Known port issue', 'notice', 'The port differs from the expected behavior. This is a recorded limitation.'],
    known_port_defect: ['Known port issue', 'notice', 'The port and STACK differ because of a recorded port limitation.'],
    domain_review: ['Domain/branch difference', 'notice', 'The engines use different assumptions or symbolic conventions. The intended assumptions need clarification with STACK.'],
    proof_limitation: ['Unproved identity', 'notice', 'The port cannot certify the desired identity; its required domain and exact proof need review.'],
    known_native_mathematical_failure: ['Known STACK issue', 'notice', 'A reviewed case where STACK differs from the expected behavior.'],
    known_port_limitation: ['Known applicability difference', 'notice', 'The final mark agrees, but the engines differ about whether the answer test applies.'],
    approved_difference: ['Documented difference', 'notice', 'The engines differ in a specifically reviewed way.'],
    branch_convention_difference: ['Different root convention', 'notice', 'The port uses principal complex powers; STACK uses a real odd root in this case.'],
    match: ['Same result', 'good', 'The compared observations agree. Agreement alone does not establish correctness.'],
    same_boundary: ['Same input handling', 'neutral', 'Python and the browser agree on an invalid or unsupported input, rather than on a graded answer.'],
    match_controlled_error: ['Same expected error', 'good', 'Both implementations report the asserted controlled error.'],
    match_desired: ['As expected', 'good', 'STACK produced the expected answer-test result.'],
    matches_desired: ['As expected', 'good', 'STACK produced the expected answer-test result.'],
    out_of_contract: ['Outside port scope', 'neutral', 'This case uses a feature the port does not yet support.'],
    outside_port_scope: ['Not run for input checks', 'neutral', 'This suite does not run the native comparison for these invalid or unsupported input checks.'],
    port_test_unsupported: ['Answer test not yet implemented in port', 'neutral', 'The port does not implement this answer test. The comparison runner therefore did not invoke STACK for this family. This is a port coverage gap, not a missing STACK feature.'],
    reference_preparation_not_run: ['STACK not run: input preparation needed', 'neutral', 'This direct-call comparison did not invoke STACK because the input needs parser or controller handling. See the specific reason in the case.'],
    port_not_supported: ['Input or feature not yet supported by port', 'neutral', 'The port implements this answer test, but does not yet support this input type, syntax, mathematical domain, or option. See the case’s specific reason.'],
    port_input_error: ['Port reported an input/reference error', 'neutral', 'The port reported a problem reading the answer, model answer, or test setting instead of giving a mark. This does not establish that the original STACK input was invalid.'],
    no_mark_comparison: ['No mark comparison', 'neutral', 'Both engines did not produce comparable accept/reject marks.'],
    no_applicability_comparison: ['No applicability comparison', 'neutral', 'Both engines did not produce comparable applicability flags.'],
    not_compared: ['Not compared', 'neutral', 'There are no comparable observations for this comparison.'],
    unavailable: ['No result available', 'neutral', 'The runner or a comparable saved result is unavailable.'],
    unsupported: ['Unsupported', 'neutral', 'The operation is outside the supported subset.'],
    upstream_negative_sentinel_difference: ['Source-flagged difference', 'notice', 'Upstream flags a STACK deviation; this run has no case-specific review of it.'],
    unexpected: ['Unexpected result', 'bad', 'The observation does not meet the recorded expectation.'],
    unexpected_stale_exception: ['Resolved issue needs review', 'bad', 'A recorded exception no longer matches; the expectation must be reviewed.'],
    unexpected_mismatch: ['Unreviewed difference', 'bad', 'The engines differ without a matching case-specific explanation.'],
    unexpected_execution_error: ['Execution error', 'bad', 'A runner failed to produce a valid observation.'],
    unexpected_native_deviation: ['Unexpected STACK result', 'bad', 'STACK differs from the expected result without a reviewed explanation.'],
    expected_controlled_error_not_observed: ['Expected error missing', 'bad', 'The expected controlled error was not observed.'],
    mismatch: ['Different results', 'bad', 'The compared observations differ.'],
    error: ['Execution error', 'bad', 'The runner failed to produce a valid observation.'],
    failed: ['Check failed', 'bad', 'This saved check did not meet its expectations.'],
  };
  const state = key => states[key] || ['Unclassified result', 'neutral', `Raw status: ${key}`];
  const badge = (title, key) => {
    const [text, tone, explanation] = state(key);
    const el = node('span', `${title}: ${text}`, `result-badge tone-${tone}`);
    el.title = explanation;
    return el;
  };
  const details = (title, data) => {
    const el = node('details', undefined, 'technical-details');
    el.append(node('summary', title), node('pre', pretty(data)));
    return el;
  };
  const link = (url, text) => {
    if (!/^https:\/\/github\.com\//.test(url || '')) return node('span', text);
    const el = node('a', text); el.href = url; el.rel = 'noopener noreferrer'; return el;
  };
  const parityStatus = row => {
    const raw = row.parity_status;
    const observed = row.parity?.python || row.python;
    return raw === 'match' && observed?.kind !== 'result' ? 'same_boundary' : raw;
  };
  const nativeStatus = (r,key) => {
    if(r[key]!=='unavailable' || r.native?.status!=='unavailable') return r[key];
    return r.native.reason==='test_family_not_implemented' ? 'port_test_unsupported' : 'reference_preparation_not_run';
  };
  const portStatus = r => {
    if(r.desired_status==='known_defect' && ['domain_review','proof_limitation'].includes(r.discussion?.category)) return r.discussion.category;
    if(r.desired_status!=='out_of_contract') return r.desired_status;
    if((r.python?.reason || '').startsWith('answer test ')) return 'port_test_unsupported';
    return r.python?.kind==='unsupported' ? 'port_not_supported' : 'port_input_error';
  };
  const comparisonStatus = (r,key) => {
    // Name the port coverage gap first, even when the saved native field only
    // says "unavailable" or "not_compared". Reference execution is secondary.
    if(r.desired_status==='out_of_contract') return portStatus(r);
    if(r[key]==='known_port_defect' && ['domain_review','proof_limitation'].includes(r.discussion?.category)) return r.discussion.category;
    return nativeStatus(r,key);
  };
  const specs = {
    desired: {name:'Port vs expected', help:'Does this port produce the expected behavior?', get:portStatus},
    native: {name:'Port vs STACK', help:'Agreement where comparable. Other rows identify the port coverage gap or the reason no reference comparison was made.', get:r => comparisonStatus(r,'native_status')},
    parity: {name:'Browser vs Python', help:'Does the browser produce the same behavior as the Python port?', get:parityStatus},
    native_mark: {name:'Final mark agreement', help:'Do the port and STACK both accept or both reject?', get:r => r.native_mark_status==='not_compared' ? 'no_mark_comparison' : nativeStatus(r,'native_mark_status')},
    native_applicability: {name:'Test applicability', help:'Do both engines agree that this answer test can compare the supplied values?', get:r => r.native_applicability_status==='not_compared' ? 'no_applicability_comparison' : nativeStatus(r,'native_applicability_status')},
    native_desired: {name:'STACK vs expected', help:'Does STACK produce the result expected by the original test case?', get:r => r.native_desired_status==='not_compared' && r.native?.status==='unavailable' ? nativeStatus(r,'native_status') : r.native_desired_status},
  };
  const counts = (rows, spec) => rows.reduce((out,r) => {const key=spec.get(r); out[key]=(out[key]||0)+1; return out;},{});
  function comparison(key, spec, rows, cards, filters, onChange) {
    const options = counts(rows,spec);
    const control = node('label',spec.name);
    const select = node('select'); select.id = `${key}-filter`; select.setAttribute('aria-label',spec.name);
    const all = node('option','All results'); all.value=''; select.append(all);
    const ordered = Object.keys(options).sort((a,b) => {
      const rank={bad:0,notice:1,good:2,neutral:3};
      return rank[state(a)[1]]-rank[state(b)[1]] || state(a)[0].localeCompare(state(b)[0]);
    });
    for (const value of ordered) {const item=node('option',state(value)[0]); item.value=value; select.append(item);}
    control.append(select); filters.append(control); select.addEventListener('change',onChange);
    const card=node('section',undefined,'comparison-card');
    card.append(node('h3',spec.name),node('p',spec.help,'comparison-help'));
    const list=node('ul',undefined,'comparison-counts');
    for (const value of ordered) {
      const li=node('li'); const button=node('button',undefined,`count-link tone-${state(value)[1]}`); button.type='button';
      button.append(node('span',state(value)[0]),node('strong',options[value]));
      button.title=state(value)[2]; button.addEventListener('click',()=>{select.value=value;onChange();$('case-results')?.scrollIntoView({block:'start'});});
      li.append(button);list.append(li);
    }
    card.append(list);cards.append(card);return select;
  }
  const outcome = (value, expected=false) => {
    if (!value) return 'No result available';
    if (value.kind === 'controlled_error') return `Error expected${value.error_kind ? ' ('+value.error_kind.replaceAll('_',' ')+')' : ''}`;
    if (value.kind === 'unsupported') return 'Unsupported';
    const errors={invalid_student:'Invalid input',invalid_teacher:'Invalid reference answer',invalid_option:'Invalid test option',unexpected_exception:'Execution error',timeout:'Timed out'};
    if (errors[value.kind]) return errors[value.kind];
    if (value.status && value.status !== 'ok') return value.status === 'error' ? 'Execution error' : 'Not run by reference harness';
    if (value.controlled_error === true) return 'Controlled error reported';
    if (typeof value.correct === 'boolean') return value.correct ? 'Accept' : 'Reject';
    return expected ? 'See expected behavior below' : 'No graded result';
  };
  function outcomes(expected, python, native, parity) {
    const table=node('table',undefined,'outcome-table');
    const head=node('thead');const tr=node('tr');for(const title of ['Result','Accept / reject / error','Test applies'])tr.append(node('th',title));head.append(tr);table.append(head);
    const body=node('tbody');
    for (const [title,value,isExpected] of [['Expected',expected,true],['Port (Python)',python,false],['STACK (Maxima)',native,false],['Port (browser)',parity?.pyodide,false]]) {
      const row=node('tr');const applies=value?.cas_valid;
      row.append(node('th',title),node('td',outcome(value,isExpected)),node('td',typeof applies==='boolean' ? applies ? 'Yes' : 'No' : '—'));
      body.append(row);
    }
    table.append(body);return table;
  }
  function expressions(student, teacher) {
    const line=node('div',undefined,'case-expressions');
    for (const [title,text] of [['Submitted',student],['Reference',teacher]]) {const p=node('p');p.append(node('span',title+': '),node('code',text));line.append(p);}return line;
  }
  const caseTitle = row => ({
    'port-principal-root-control':'Negative-number root convention',
    'port-complex-root-form':'Equivalent complex values, different written forms',
    'port-complex-principal-root':'Complex fifth-root identity',
    'port-division-form-limitation':'Division preserves written sign placement',
    'port-probe-collision':'Matching samples do not prove equivalence',
    'port-singular-probe':'Numerical screening near a pole',
    'port-exact-not-tolerance':'Equivalence requires exact equality',
    'port-cosh':'Hyperbolic identity',
    'port-logistic':'Logistic and hyperbolic forms',
    'port-held-calculus':'Held differentiation is outside scope',
    'port-base-log':'Base-logarithm notation is outside scope',
    'port-plus-minus':'Plus/minus notation is outside scope',
  }[row.id] || row.id.replace(/^port-/,'').replaceAll('-',' ').replace(/^./,x=>x.toUpperCase()));
  const testHelp = name => ({AlgEquiv:'AlgEquiv checks equivalence.',EqualComAss:'EqualComAss checks equivalence and written form; equivalent values may still be rejected.',FacForm:'FacForm checks equivalence and factorized form.',SingleFrac:'SingleFrac checks equivalence and a single written fraction.',LowestTerms:'LowestTerms checks the written fraction’s form, not its value against the reference.',NumAbsolute:'NumAbsolute uses an absolute numerical tolerance.',NumRelative:'NumRelative uses a relative numerical tolerance.',NumDecPlaces:'NumDecPlaces checks the value and the written decimal places.'}[name] || `${name} is the source answer test.`);
  function conclusion(row, port=false) {
    const status=port ? row.python_status : row.desired_status;
    if (status==='known_defect' && row.discussion?.category==='domain_review') return 'Domain or branch difference: the port rejects an identity that STACK accepts. The required assumptions or conventions need to be stated.';
    if (status==='known_defect' && row.discussion?.category==='proof_limitation') return 'Unproved identity: the desired acceptance is not yet certified by the port. This is separate from an intentional convention difference.';
    if (row.native_status==='branch_convention_difference') return 'Known compatibility difference: the port rejects this equality using the principal complex fifth root. STACK accepts it using the negative real fifth root. The browser agrees with the port. This is a difference in root conventions.';
    if (status==='known_defect') return 'Known port issue: the port does not produce the expected answer-test result. Browser agreement does not resolve this limitation.';
    if (status==='boundary_pass') return row.expected?.kind==='unsupported' ? 'This notation is not supported, as expected. No mathematical answer was graded.' : 'The answer is correctly reported as invalid. No mathematical answer was graded.';
    if (status==='out_of_contract') return `${state(portStatus(row))[0]}. This row records a port coverage gap or input error, not successful compatibility.`;
    if (row.native_status==='known_native_mathematical_failure' || row.native_desired_status==='known_native_mathematical_failure') return 'Reviewed STACK issue: the native result differs from the expected behavior. See the case-specific explanation below.';
    if (String(status).startsWith('unexpected')) return 'This result needs investigation: it does not meet the recorded expectation.';
    return 'Read “Accept” or “Reject” in the context of the named answer test. A check can succeed because it correctly rejects an answer.';
  }
  return {$,node,pretty,state,badge,details,link,specs,comparison,parityStatus,outcomes,expressions,testHelp,conclusion,caseTitle};
})();
