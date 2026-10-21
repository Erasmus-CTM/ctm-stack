// Run after installing the pinned umbrella's npm dependencies:
// node tests/compare-rendered/stack-checkers-0.10.test.cjs <umbrella>/tools/compare-rendered.mjs
// The comparator has one home in ctm-assessment; never copy it into this repo.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cp = require('node:child_process');
const {createRequire} = require('node:module');

const root = path.resolve(__dirname, '../..');
const comparator = path.resolve(process.argv[2] || '_ci/ctm-assessment/tools/compare-rendered.mjs');
const {JSDOM} = createRequire(comparator)('jsdom');
const baseSHA = '1b1d50f69fc1e7eb39846b497657d72be325f597';
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'stack-rendered-expectations-'));
const expect = path.join(__dirname, 'stack-checkers-0.10.yml');

function run(command, args, options = {}) {
  const result = cp.spawnSync(command, args, {encoding: 'utf8', ...options});
  assert.equal(result.status, 0, `${command} ${args.join(' ')}\n${result.error || ''}\n${result.stderr}\n${result.stdout}`);
  return result.stdout;
}

function compare(before, after, accepted, label) {
  for (const [side, html] of [['before', before], ['after', after]]) {
    const dir = path.join(temp, 'comparison', side, 'docs');
    fs.mkdirSync(dir, {recursive: true});
    fs.writeFileSync(path.join(dir, 'authoring.html'), html);
  }
  const report = path.join(temp, 'report.json');
  const result = cp.spawnSync(process.execPath, [comparator,
    '--before', path.join(temp, 'comparison/before'),
    '--after', path.join(temp, 'comparison/after'), '--expect', expect,
    '--report', report], {encoding: 'utf8'});
  assert.equal(result.status, accepted ? 0 : 1, `${label}: ${result.stderr}\n${result.stdout}`);
  const data = JSON.parse(fs.readFileSync(report, 'utf8'));
  assert.ok(data.summary.differences > 0, `${label}: mutation did not change the page`);
  assert.equal(data.summary.unexpected === 0, accepted, label);
  console.log(`PASS ${label} (${data.summary.unexpected} unexplained)`);
  return data;
}

try {
  const baseline = process.env.STACK_RENDERED_BASE_QMD
    ? fs.readFileSync(process.env.STACK_RENDERED_BASE_QMD, 'utf8')
    : run('git', ['show', `${baseSHA}:docs/authoring.qmd`], {cwd: root});
  const rendered = [];
  for (const [side, source] of [['base', baseline], ['head', fs.readFileSync(path.join(root, 'docs/authoring.qmd'), 'utf8')]]) {
    const dir = path.join(temp, side);
    fs.mkdirSync(dir);
    fs.writeFileSync(path.join(dir, 'authoring.qmd'), source);
    // Render outside the project: these prose changes need no question engine.
    run('quarto', ['render', 'authoring.qmd', '--to', 'html', '--quiet'], {cwd: dir});
    rendered.push(fs.readFileSync(path.join(dir, 'authoring.html'), 'utf8'));
  }
  const [before, after] = rendered;
  const reviewed = compare(before, after, true, 'reviewed guide changes');
  assert.equal(reviewed.summary.differences, 136);
  assert.deepEqual(Object.fromEntries(Object.entries(reviewed.summary.categories).map(([id, c]) => [id, c.differences])), {
    'docs-requirements': 5, 'docs-question-options-and-checkanswertype': 74,
    'docs-numerical-tests': 21, 'docs-same-type-and-undecided': 36,
  });
  const mutate = (label, change) => {
    const dom = new JSDOM(after);
    change(dom.window.document);
    compare(before, dom.serialize(), false, label);
    dom.window.close();
  };
  for (const id of ['question-block-options', 'input-and-xml-reference', 'answer-entry-and-form', 'lists-sets-and-equations']) {
    mutate(`${id}: unrelated prose`, doc => doc.querySelector(`#${id} p`).append(' Unreviewed grading policy.'));
    mutate(`${id}: unrelated button`, doc => {
      const button = doc.createElement('button');
      button.className = 'stack-check';
      button.textContent = 'Unreviewed grading action';
      doc.getElementById(id).append(button);
    });
  }
  mutate('reversed numerical advice', doc => {
    const p = [...doc.querySelectorAll('#answer-entry-and-form p')].find(p => p.textContent.includes('approximate measurement'));
    assert.ok(p, 'numerical advice paragraph');
    p.textContent = 'Use algebraic equivalence as a tolerance test for every approximate measurement.';
  });
  mutate('removed prose', doc => doc.querySelector('#answer-entry-and-form p').remove());
  mutate('changed attribute', doc => doc.querySelector('#answer-entry-and-form p').className = 'unreviewed');
  mutate('added question data', doc => {
    const data = doc.createElement('script');
    data.type = 'application/json';
    data.className = 'stack-question-data';
    data.textContent = '{"score":0}';
    doc.getElementById('answer-entry-and-form').append(data);
  });
} finally {
  fs.rmSync(temp, {recursive: true, force: true});
}
