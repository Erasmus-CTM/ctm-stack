<?php
// SPDX-License-Identifier: AGPL-3.0-or-later
// Test-only upstream oracle. No source modifications, database or CAS subprocess.
declare(strict_types=1);
ini_set('display_errors', 'stderr');
set_error_handler(function ($severity, $message, $file, $line) {
    throw new ErrorException($message, 0, $severity, $file, $line);
});
$stack = $argv[1];
require_once('../config.php');
require_once($stack . '/api/emulation/MoodleEmulation.php');
require_once($stack . '/stack/prt.class.php');
require_once($stack . '/stack/prt.evaluatable.class.php');
require_once($stack . '/stack/questiontestresult.php');
$request = json_decode(file_get_contents('php://stdin'), true, 512, JSON_THROW_ON_ERROR);
$report = ['schema' => 1, 'php' => PHP_VERSION, 'scores' => [], 'castext' => [], 'graphs' => [], 'paint' => []];

// Exercise the public PRT score API, not just its numerical utility.
$round = new ReflectionMethod(stack_question_test_result::class, 'round_prt_scores');
$round->setAccessible(true);
$testresult = (new ReflectionClass(stack_question_test_result::class))->newInstanceWithoutConstructor();
for ($i = 0; $i <= 1000; $i++) {
    $raw = $i / 1000;
    $value = new prt_evaluatable('prt_audit()', 1, new castext2_static_replacer([]), []);
    $value->set_cas_evaluated_value('[[],'. json_encode($raw) . ',0.1,"",[]]');
    $value->set_cas_status([], [], []);
    $actual = $value->get_score();
    $report['scores'][] = ['raw' => $raw, 'actual' => $actual,
        'testExpected' => $round->invoke($testresult, $raw),
        'testActual' => $round->invoke($testresult, $actual),
        'penalty' => $value->get_penalty()];
}

// Compile real author text through the unmodified CASText compiler. Return
// the program for evaluation in the owned native runtime, then PHP replaces
// its result in a second phase using exactly the same static map.
foreach ($request['texts'] ?? [] as $id => $source) {
    $map = new castext2_static_replacer([]);
    try {
        $compiled = castext2_parser_utils::compile($source, FORMAT_HTML,
            ['context' => 'audit/'.$id, 'static string extractor' => $map])->toString();
        $report['castext'][] = ['id' => $id, 'source' => $source,
            'expression' => 'block([x:1],'.$compiled.')', 'map' => $map->get_map()];
    } catch (Throwable $error) {
        $report['castext'][] = ['id' => $id, 'source' => $source, 'error' => $error->getMessage()];
    }
}
foreach ($request['paint'] ?? [] as $row) {
    // API emulation declares string constants; Moodle uses integers. Always
    // select the actual upstream constant, avoiding a harness type mismatch.
    $format = $row['format'] == 4 ? FORMAT_MARKDOWN : FORMAT_HTML;
    $ast = castext2_parser_utils::parse($row['source'], $format);
    $modes = [];
    $ast->callbackRecurse(function ($node) use (&$modes) {
        if ($node instanceof CTP_Block && $node->name === 'latex') {
            $modes[] = $node->mathmode;
        }
        return true;
    });
    $report['paint'][] = $row + ['actual' => $modes];
}
foreach ($request['replacements'] ?? [] as $row) {
    $map = new castext2_static_replacer($row['map']);
    $restored = $map->replace($row['value']);
    $rendered = is_array($restored) ? castext2_parser_utils::postprocess_parsed(
        $restored, null, new castext2_placeholder_holder()) : $restored;
    $report['castext'][] = ['id' => $row['id'], 'value' => $restored, 'rendered' => $rendered];
}

foreach ($request['graphs'] ?? [] as $graph) {
    $nodes = [];
    foreach ($graph['nodes'] as $index => $node) {
        $n = (object)['nodename' => (string)$index, 'answertest' => 'AlgEquiv',
            'sans' => (string)$index, 'tans' => '1', 'testoptions' => '', 'quiet' => 0];
        foreach (['true', 'false'] as $side) {
            $branch = $node[$side];
            foreach (['mode' => 'scoremode', 'score' => 'score', 'next' => 'nextnode', 'note' => 'answernote'] as $from => $to) {
                $n->{$side.$to} = $branch[$from] === null ? '-1' : (string)$branch[$from];
            }
            $n->{$side.'penalty'} = '';
            $n->{$side.'feedback'} = '';
            $n->{$side.'feedbackformat'} = FORMAT_HTML;
        }
        $nodes[(string)$index] = $n;
    }
    $model = (object)['name' => 'audit', 'autosimplify' => true, 'feedbackstyle' => 1,
        'feedbackvariables' => '', 'nodes' => $nodes, 'firstnodename' => '0'];
    $compiler = new stack_potentialresponse_tree_lite($model, 1);
    $compiled = $compiler->compile([], [], $graph['penalty'], new stack_cas_security(),
        'audit/prt', new castext2_static_replacer([]));
    $report['graphs'][] = ['id' => $graph['id'], 'compiled' => $compiled];
}
echo json_encode($report, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE), "\n";
