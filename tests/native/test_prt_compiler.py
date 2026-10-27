"""Compiler invariants and independent graph/arithmetic reference.

The optional native audit executes the emitted programs in runtime-v3. Its
reference follows one path and uses decimal arithmetic; it does not evaluate
the emitter's topological guards or treat upstream output as ground truth.
"""
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_EVEN
import importlib.util
from pathlib import Path
import random
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ctm_prt_audit',ROOT/'_extensions/ctm-stack/native/prt_compiler.py')
prt=importlib.util.module_from_spec(spec);sys.modules[spec.name]=prt;spec.loader.exec_module(prt)


def example():
    branch=lambda mode,score,next,note:prt.Branch(mode,score,next,note,None)
    predicate=lambda key:prt.NativeTest('AlgEquiv',str(key),'1','','',False,True,False)
    nodes=(prt.Decision('0',predicate(0),branch('=',.8,'1','0T'),branch('=',.2,'2','0F'),False),
           prt.Decision('1',predicate(1),branch('+',.7,'3','1T'),branch('-',.9,'3','1F'),False),
           prt.Decision('2',predicate(2),branch('*',.5,'3','2T'),branch('=',.618,'3','2F'),False),
           prt.Decision('3',predicate(3),branch('+',0,None,'3T'),branch('-',0,None,'3F'),False))
    return prt.ResponseTree('audit',nodes,(),(),None,True,.1)


def expected(tree,verdicts):
    """Independent path specification: no compiler ordering or native calls."""
    nodes={node.id:node for node in tree.nodes};key=tree.start;score=Decimal(0);notes=[];visited=[]
    while key is not None:
        assert key not in visited
        visited.append(key);node=nodes[key]
        branch=node.on_true if verdicts[int(key)] else node.on_false
        value=Decimal(str(branch.score))
        if branch.mode=='=':score=value
        elif branch.mode=='+':score+=value
        elif branch.mode=='-':score-=value
        elif branch.mode=='*':score*=value
        else:raise AssertionError('Unknown mode in reference')
        notes.append(branch.note);key=branch.next_node
    rounded=lambda x:float(min(Decimal(1),max(Decimal(0),x)).quantize(Decimal('.001'),rounding=ROUND_HALF_EVEN))
    return {'score':rounded(score),'penalty':rounded(Decimal(str(tree.penalty))),'notes':notes,'visited':visited}


def test_independent_paths_clip_and_multiplication():
    tree=example()
    assert expected(tree,[True,True,False,True])['score']==1
    assert expected(tree,[True,False,False,True])['score']==0
    assert expected(tree,[False,False,True,True])['score']==.1
    assert expected(tree,[False,False,False,True])['score']==.618
    compiled=prt.compile_tree(tree)
    assert compiled['function']=='ctm_prt_audit'
    assert 'ctm_active' in compiled['def'] and '%_EXITS' not in compiled['def']


@pytest.mark.parametrize('defect',['cycle','dangling','unreachable','duplicate','mode','infinite','reserved'])
def test_malformed_graphs_and_resources_fail_closed(defect):
    tree=example();nodes=list(tree.nodes)
    if defect=='cycle':nodes[-1]=replace(nodes[-1],on_true=replace(nodes[-1].on_true,next_node='0'))
    if defect=='dangling':nodes[0]=replace(nodes[0],on_true=replace(nodes[0].on_true,next_node='9'))
    if defect=='unreachable':nodes[0]=replace(nodes[0],on_true=replace(nodes[0].on_true,next_node='2'))
    if defect=='duplicate':nodes.append(nodes[0])
    if defect=='mode':nodes[0]=replace(nodes[0],on_true=replace(nodes[0].on_true,mode='?'))
    if defect=='infinite':nodes[0]=replace(nodes[0],on_true=replace(nodes[0].on_true,score=float('inf')))
    if defect=='reserved':tree=replace(tree,arguments=('ctm_score',))
    with pytest.raises(ValueError):prt.compile_tree(replace(tree,nodes=tuple(nodes)))


def test_python_checker_rejects_an_untyped_continuation_descriptor():
    tree=example();node=replace(tree.nodes[0],predicate=prt.PythonCheck({'entry':'stack.check'}))
    with pytest.raises(ValueError,match='continuation'):
        prt.compile_tree(replace(tree,nodes=(node,*tree.nodes[1:])))


def test_python_checker_emits_an_explicit_native_pause_and_resume():
    tree=example()
    descriptor={'sans':'ans','teacher':'1','options':{'checker':'check'}}
    node=replace(tree.nodes[1],predicate=prt.PythonCheck(descriptor))
    compiled=prt.compile_tree(replace(tree,nodes=(tree.nodes[0],node,*tree.nodes[2:])))
    assert compiled['continuations']=={'1':descriptor}
    assert compiled['sig']=='ctm_prt_audit(false,false)'
    assert 'CTM_PYTHON' in compiled['def'] and 'ctm_resume' in compiled['def']


def programs():
    """Diverse small DAGs, all verdict assignments, fixed reproducible seed."""
    rng=random.Random(20261027);rows=[]
    for graph in range(120):
        count=rng.randrange(2,7);nodes=[]
        for index in range(count):
            targets=[str(n) for n in range(index+1,count)]+[None]
            # At least the true path reaches every node. False edges can skip
            # and converge, so no topological traversal is the oracle.
            true_next=str(index+1) if index+1<count else None
            false_next=rng.choice(targets)
            branches=[prt.Branch(rng.choice(['=','+','-','*']),rng.choice([0,.1,.2,.333,.5,.618,.999,1,1.2,-.2]),
                nextnode,str(index)+side,None) for nextnode,side in [(true_next,'T'),(false_next,'F')]]
            nodes.append(prt.Decision(str(index),prt.NativeTest('AlgEquiv',str(index),'1','','',False,True,False),*branches,False))
        tree=prt.ResponseTree('audit',tuple(nodes),(),(),None,True,rng.choice([0,.1,.333,.618,1.2]))
        compiled=prt.compile_tree(tree)
        for bits in range(1<<count):
            verdicts=[bool(bits&(1<<n)) for n in range(count)]
            members=','.join(str(n) for n,v in enumerate(verdicts) if v)
            expression='block([ctm_verdicts:{'+members+'}],local(ATAlgEquiv,ctm_prt_audit),'
            expression+='ATAlgEquiv(s,t):=[true,member(s,ctm_verdicts),string(s),""],'+compiled['def']+','+compiled['sig']+')'
            rows.append({'id':str(graph)+'/'+str(bits),'expression':expression,'expected':expected(tree,verdicts)})
    return rows


def test_audit_inventory_exercises_many_paths():
    rows=programs()
    assert len(rows)>2000
    assert any(row['expected']['score']==0 for row in rows)
    assert any(row['expected']['score']==1 for row in rows)
    assert any(row['expected']['score']==.618 for row in rows)
