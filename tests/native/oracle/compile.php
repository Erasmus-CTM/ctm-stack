<?php
// SPDX-License-Identifier: AGPL-3.0-or-later
// Author-build bridge to the exact pinned upstream STACK compiler. No CAS
// evaluation, Moodle installation, database or learner request runs in PHP.
declare(strict_types=1);
ini_set('display_errors', 'stderr');
set_error_handler(function ($severity, $message, $file, $line) {
    throw new ErrorException($message, 0, $severity, $file, $line);
});
$stack = $argv[1];
require_once('../config.php');
require_once($stack . '/api/emulation/MoodleEmulation.php');
require_once($stack . '/stack/cas/ast.container.class.php');
require_once($stack . '/stack/cas/keyval.class.php');
require_once($stack . '/stack/prt.class.php');

function scoped_usage(array $usage, string $where, bool $random): void {
    $allowed = array_flip(explode(' ', 'sqrt sin cos tan sec csc cot sinh cosh tanh sech csch coth exp log ln abs '
        . 'asin acos atan asec acsc acot asinh acosh atanh asech acsch acoth cosec cosech gcd mod matrix '
        . 'diff integrate sum product expand factor ratsimp cancel ev float floor ceiling round truncate '
        . 'min max lcm num denom part length first second third last rest reverse append endcons cons '
        . 'makelist map lambda block if listp matrixp setp numberp integerp equal is subst substinpart '
        . 'set setify listify union intersection setdifference member subsetp cardinality sort '
        . 'determinant rank transpose invert ident zeromatrix diag_matrix echelon charpoly '
        . 'rand rand_with_step rand_with_prohib random_subset random_permutation '
        . 'decimalplaces dispdp displaydp significantfigures dispsf _EC %_C'));
    foreach (array_keys($usage['calls'] ?? []) as $call) {
        if (!isset($allowed[$call]) || !$random && preg_match('/^(rand|random|multiselqn)/', $call)) {
            throw new RuntimeException($where . ': unsupported native author call ' . $call);
        }
    }
    foreach (array_keys($usage['write'] ?? []) as $name) {
        if (!preg_match('/^[A-Za-z][A-Za-z0-9_]*$/D', $name) || str_starts_with($name, 'ctm_')) {
            throw new RuntimeException($where . ': unsupported native assignment name ' . $name);
        }
    }
}

function teacher(string $source, string $where, bool $random = false): array {
    $cs = stack_ast_container::make_from_teacher_source($source, $where);
    if (!$cs->get_valid()) throw new RuntimeException($where . ': ' . $cs->get_errors());
    $usage = $cs->get_variable_usage();
    scoped_usage($usage, $where, $random);
    if (!empty($usage['write'])) throw new RuntimeException($where . ': operands must not write variables');
    return [$cs->get_evaluationform(), $usage];
}

function maxima_map(array $pairs): string {
    $parts = ['"stack_map"'];
    foreach ($pairs as $key => $value) $parts[] = '[' . stack_utils::php_string_to_maxima_string((string)$key) . ',' . $value . ']';
    return '[' . implode(',', $parts) . ']';
}

try {
    $q = json_decode(file_get_contents('php://stdin'), true, 512, JSON_THROW_ON_ERROR);
    if (isset($q['scoreValues'])) {
        echo json_encode(array_map(fn($value) => ['input' => $value,
            'postprocessed' => stack_utils::fix_to_continued_fraction($value, 4)], $q['scoreValues']), JSON_THROW_ON_ERROR), "\n";
        exit(0);
    }
    $security = new stack_cas_security();
    $map = new castext2_static_replacer([]);
    $kv = new stack_cas_keyval($q['variables']);
    $kv->set_security($security);
    if (!$kv->get_valid()) throw new RuntimeException($kv->get_errors());
    $variables = $kv->compile('question/variables', $map);
    scoped_usage($variables['references'], 'question/variables', true);
    if ($variables['blockexternal'] !== null || $variables['contextvariables'] !== null
        || str_contains($q['variables'], ':=') || str_contains($q['variables'], '::')) {
        throw new RuntimeException('Native preparation currently supports scoped question assignments; functions and global declarations require a separate capability');
    }
    $bound = $variables['references']['write'];
    $inputs = array_fill_keys(array_column($q['inputs'], 'name'), true);
    if (array_intersect_key($bound, $inputs)) throw new RuntimeException('Question variables collide with student inputs');
    foreach ($q['inputs'] as $input) teacher($input['teacher'], 'input/' . $input['name'] . '/teacher');
    $prts = [];
    $feedbacknames = [];
    $math = [];
    $grading = [];
    foreach ($q['prts'] as $prt) {
        $fv = new stack_cas_keyval($prt['feedbackvariables']);
        $fv->set_security($security);
        if (!$fv->get_valid()) throw new RuntimeException($fv->get_errors());
        $fv = $fv->compile('prt/' . $prt['name'] . '/feedbackvariables', $map);
        scoped_usage($fv['references'], 'prt/' . $prt['name'] . '/feedbackvariables', false);
        if ($fv['blockexternal'] !== null || $fv['contextvariables'] !== null
            || str_contains($prt['feedbackvariables'], ':=') || str_contains($prt['feedbackvariables'], '::')) {
            throw new RuntimeException('Native feedback variables require scoped assignments');
        }
        $localnames = $fv['references']['write'];
        if (array_intersect_key($localnames, $bound + $inputs)) throw new RuntimeException('Feedback variables collide with question variables or inputs');
        $feedbacknames += $localnames;
        $nodes = [];
        $nodegrading = [];
        foreach ($prt['nodes'] as $node) {
            $resolved = [];
            foreach (['student','teacher','options'] as $field) {
                $src = $node[$field];
                $resolved[$field] = $src === '' ? '""' : 'string(' . teacher($src, 'prt/' . $prt['name'] . '/' . $node['name'] . '/' . $field)[0] . ')';
            }
            $nodegrading[$node['name']] = maxima_map($resolved);
            $n = (object)['nodename' => $node['name'], 'answertest' => $node['test'],
                'sans' => $node['student'], 'tans' => $node['teacher'], 'testoptions' => $node['options'],
                'quiet' => (int)$node['quiet']];
            foreach (['true', 'false'] as $branch) {
                foreach (['mode' => 'scoremode', 'score' => 'score', 'next' => 'nextnode',
                          'note' => 'answernote', 'feedback' => 'feedback'] as $from => $to) {
                    $n->{$branch . $to} = (string)$node[$branch][$from];
                }
                $n->{$branch . 'penalty'} = '';
                $n->{$branch . 'feedbackformat'} = FORMAT_HTML;
            }
            $nodes[$node['name']] = $n;
        }
        $model = (object)['name' => $prt['name'], 'autosimplify' => $prt['autosimplify'],
            'feedbackstyle' => 1, 'feedbackvariables' => $prt['feedbackvariables'],
            'nodes' => $nodes, 'firstnodename' => '0'];
        $compiler = new stack_potentialresponse_tree_lite($model, $prt['value']);
        $prts[$prt['name']] = $compiler->compile($inputs, $bound, $q['penalty'], $security,
            'question/prt/' . $prt['name'], $map);
        $grading[$prt['name']] = 'block([' . implode(',', array_keys($localnames)) . '],simp:' . ($prt['autosimplify'] ? 'true' : 'false') . ','
            . ($fv['statement'] === null ? '' : $fv['statement'] . ',') . 'simp:false,' . maxima_map($nodegrading) . ')';
    }
    $texts = [];
    foreach (['questiontext', 'generalfeedback', 'specificfeedback', 'questionnote'] as $field) {
        foreach (castext2_parser_utils::get_casstrings($q[$field]) as $cs) {
            if (!$cs->get_valid()) throw new RuntimeException($field . ': invalid CASText expression');
            scoped_usage($cs->get_variable_usage(), $field, false);
            $math[] = 'string(' . $cs->get_evaluationform() . ')';
        }
        $texts[$field] = castext2_parser_utils::compile($q[$field], FORMAT_HTML,
            ['context' => 'question/' . $field, 'bound-vars' => $bound,
             'static string extractor' => $map])->toString();
    }
    $testinputs = [];
    foreach ($q['qtests'] as $test) {
        $fields = [];
        foreach ($test['inputs'] as $key => $source) {
            if (str_starts_with($source, 'CT:')) throw new RuntimeException('CASText test inputs need a separate native capability');
            if (str_starts_with($source, 'RAW:')) $fields[$key] = stack_utils::php_string_to_maxima_string(substr($source, 4));
            else {
                $cs = stack_ast_container::make_from_teacher_source($source);
                if ($cs->get_valid()) {
                    scoped_usage($cs->get_variable_usage(), 'question test input', false);
                    $fields[$key] = 'string(' . $cs->get_evaluationform() . ')';
                } else $fields[$key] = stack_utils::php_string_to_maxima_string($source);
            }
        }
        $testinputs[] = maxima_map($fields);
    }
    $string = [];
    require($stack . '/lang/en/qtype_stack.php');
    $messages = array_filter($string, fn($key) => str_starts_with($key, 'AT')
        || str_starts_with($key, 'irred_') || str_starts_with($key, 'FacForm_') || $key === 'Subst', ARRAY_FILTER_USE_KEY);
    echo json_encode(['schema' => 1, 'variables' => $variables, 'prts' => $prts,
        'texts' => $texts, 'statics' => $map->get_map(), 'language' => [
            'schema' => 1, 'stackRevision' => '33383047af39c204bf4442802a058f8b918b2b1b',
            'language' => 'en', 'messages' => $messages, 'latexReplacements' => get_stack_maxima_latex_replacements()],
        'feedbackNames' => array_keys($feedbacknames), 'grading' => maxima_map($grading),
        'math' => '[' . implode(',', $math) . ']', 'testInputs' => '[' . implode(',', $testinputs) . ']',
        'includedFiles' => get_included_files()], JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE), "\n";
} catch (Throwable $error) {
    fwrite(STDERR, 'STACK compiler: ' . $error->getMessage() . "\n");
    exit(1);
}
