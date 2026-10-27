"""Compile a checked PRT intermediate representation into scoped Maxima.

This is a compiler, not a Python response-tree interpreter. Native tests run
in runtime-v3. The IR distinguishes Python checker calls so a later explicit
continuation implementation can reuse the existing H1 checker contract.

Semantics are tested independently and compared with pinned STACK; upstream
PHP is a reference, not the specification of mathematical correctness.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re


def quote(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"')+'"'


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',value) or value.startswith('ctm_'):
        raise ValueError('Invalid PRT identifier')
    return value


def numeric(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('PRT scores and penalties must be finite numbers')
    return str(value)


@dataclass(frozen=True)
class NativeTest:
    name: str
    student: str
    teacher: str
    options: str
    raw_name: str
    required_options: object
    simplify: bool
    requires_raw: bool


@dataclass(frozen=True)
class PythonCheck:
    """An explicit continuation boundary; never masquerades as a native AT."""
    descriptor: object


@dataclass(frozen=True)
class Branch:
    mode: str
    score: object
    next_node: str | None
    note: str
    feedback: str | None


@dataclass(frozen=True)
class Decision:
    id: str
    predicate: NativeTest | PythonCheck
    on_true: Branch
    on_false: Branch
    quiet: bool


@dataclass(frozen=True)
class ResponseTree:
    name: str
    nodes: tuple
    arguments: tuple
    feedback_names: tuple
    feedback_program: str | None
    simplify: bool
    penalty: object
    start: str = '0'


def tree_from_model(model,parsed,traits):
    nodes=[]
    for node in model['nodes']:
        source=parsed['nodes'][node['name']]
        if node['test']=='PythonChecker':
            predicate=PythonCheck(node['options'])
        else:
            flags=traits[node['test']]
            predicate=NativeTest(node['test'],source['student'],source['teacher'],source['options'],node['student'].strip(),
                flags['options'],flags['simplify'],flags['raw'])
        branches=[]
        for side in ['true','false']:
            branch=node[side]
            branches.append(Branch(branch['mode'],branch['score'],None if branch['next']==-1 else str(branch['next']),
                branch['note'],source[side+'Feedback']))
        nodes.append(Decision(node['name'],predicate,*branches,node['quiet']))
    return ResponseTree(model['name'],tuple(nodes),tuple(parsed['required']),tuple(parsed['feedbackNames']),
        parsed['feedbackStatement'],model['autosimplify'],parsed['defaultPenalty'])


def topological(tree):
    """Validate the graph and produce a deterministic Kahn order.

    Execution uses one active-node label. This differs deliberately from
    upstream's reverse-postorder and accumulated-exit-set implementation.
    """
    nodes={node.id:node for node in tree.nodes}
    if len(nodes)!=len(tree.nodes) or tree.start not in nodes or not nodes:
        raise ValueError('PRT needs unique nodes and an explicit start')
    edges={key:set() for key in nodes};incoming={key:0 for key in nodes}
    for node in tree.nodes:
        for branch in [node.on_true,node.on_false]:
            if branch.mode not in ('=','+','-','*'):
                raise ValueError('Unknown PRT score mode: '+branch.mode)
            numeric(branch.score)
            if branch.next_node is not None:
                if branch.next_node not in nodes:
                    raise ValueError('PRT has a dangling next node')
                edges[node.id].add(branch.next_node)
        for target in edges[node.id]:
            incoming[target]+=1
    reached=set();pending=[tree.start]
    while pending:
        key=pending.pop()
        if key in reached:
            continue
        reached.add(key);pending.extend(edges[key])
    if reached!=set(nodes):
        raise ValueError('PRT contains unreachable nodes')
    ready=[key for key in nodes if incoming[key]==0];ordered=[]
    while ready:
        key=ready.pop(0);ordered.append(nodes[key])
        for target in edges[key]:
            incoming[target]-=1
            if incoming[target]==0:
                ready.append(target)
        ready.sort(key=lambda key:list(nodes).index(key))
    if len(ordered)!=len(nodes):
        raise ValueError('PRT contains a cycle')
    return ordered


def compile_tree(tree):
    identifier(tree.name);numeric(tree.penalty)
    arguments=[identifier(n) for n in tree.arguments]
    if len(arguments)!=len(set(arguments)) or len(arguments)>32:
        raise ValueError('PRT argument list is invalid')
    ordered=topological(tree)
    native_raw=any(isinstance(n.predicate,NativeTest) and n.predicate.requires_raw for n in ordered)
    if native_raw:
        arguments.append('_INPUT_STRING')
    function='ctm_prt_'+tree.name
    signature=function+'('+','.join(arguments)+')'
    internal=['ctm_score:0','ctm_penalty:0','ctm_feedback:""','ctm_path:[]','ctm_notes:[]',
        'ctm_active:'+quote(tree.start),'ctm_test','ctm_caught','ctm_delta','simp',
        '%ERR:["stack_map"]','%NOTES:["stack_map"]','%FEEDBACK:["stack_map"]']
    locals_=internal+[identifier(n) for n in tree.feedback_names]
    body=['simp:'+('true' if tree.simplify else 'false')]

    def checked(expression,where):
        # Preserve internal-fault classification across an authored compiled
        # function. A nested errcatch must not turn a runtime fault into a
        # mathematical false branch or reuse an earlier test's temporary.
        return ['ctm_caught:ctm_classified_errcatch('+expression+')',
            'if ctm_caught[1]#"ok" then return(["CTM_PRT_ERROR",ctm_caught[1],'+quote(where)+'])',
            'if length(%ERR)>1 then return(["CTM_PRT_ERROR","author",'+quote(where)+'])']

    if tree.feedback_program:
        body.extend(checked(tree.feedback_program,'feedback variables'))
    for node in ordered:
        if isinstance(node.predicate,PythonCheck):
            raise ValueError('PythonChecker requires the H1 native continuation capability (M4d)')
        test=node.predicate;identifier(test.name)
        args=[test.student,test.teacher]
        if test.required_options is True or test.required_options=='optional' and test.options:
            if not test.options:
                raise ValueError('Answer-test options are required for '+test.name)
            args.append('ev('+test.options+',simp)')
        if test.requires_raw:
            args.append('stackmap_get_ifexists(_INPUT_STRING,'+quote(test.raw_name)+')')
        expression='AT'+test.name+'('+','.join(args)+')'
        steps=['simp:'+('true' if test.simplify else 'false'),*checked(expression,'node '+node.id),
            'ctm_test:ctm_caught[2]',
            'if not listp(ctm_test) or length(ctm_test)<2 then return(["CTM_PRT_ERROR","author","Malformed answer-test result"])',
            'simp:true','ctm_path:endcons(ctm_test,ctm_path)']
        if not node.quiet:
            steps.append('if length(ctm_test)>3 and stringp(ctm_test[4]) and slength(ctm_test[4])>0 then ctm_feedback:castext_concat(ctm_feedback,["%strans",ctm_test[4]])')
        branches=[]
        for branch in [node.on_true,node.on_false]:
            score='ctm_delta' if branch.mode=='=' else 'ctm_score'+branch.mode+'ctm_delta'
            actions=['ctm_notes:endcons('+quote(branch.note)+',ctm_notes)','ctm_delta:'+numeric(branch.score),
                'ctm_score:'+score,'ctm_penalty:'+numeric(tree.penalty),
                'ctm_active:'+('false' if branch.next_node is None else quote(branch.next_node))]
            if branch.feedback:
                actions.append('simp:'+('true' if tree.simplify else 'false'))
                actions.extend(checked('ctm_feedback:castext_concat(ctm_feedback,'+branch.feedback+')','node '+node.id+' feedback'))
            branches.append('('+','.join(actions)+')')
        steps.append('if ctm_test[2] then '+branches[0]+' else '+branches[1])
        body.append('if is(ctm_active='+quote(node.id)+') then ('+','.join(steps)+')')
    body.extend(['simp:true',
        "ctm_score:ev('float('round('max('min(ctm_score,1.0),0.0)*1000)/1000),nouns,simp)",
        "ctm_penalty:ev('float('round('max('min(ctm_penalty,1.0),0.0)*1000)/1000),nouns,simp)",
        '[ctm_path,ctm_score,ctm_penalty,ctm_feedback,ctm_notes]'])
    return {'function':function,'sig':signature,'def':signature+':=block(['+','.join(locals_)+'],'+','.join(body)+')',
        'required':dict.fromkeys(tree.arguments,True)}


def compile_ir(question,parsed):
    if parsed.get('schema')!=1:
        raise ValueError('Unknown compiler IR schema')
    parsed=dict(parsed)
    parsed['prts']={model['name']:compile_tree(tree_from_model(model,parsed['prts'][model['name']],parsed['answerTests']))
                    for model in question['prts']}
    parsed.pop('answerTests')
    return parsed
