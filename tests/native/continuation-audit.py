#!/usr/bin/env python3
"""Generate mixed native/Python trees against the independent path reference."""
from dataclasses import replace
import json
from pathlib import Path
import runpy
import sys

reference=runpy.run_path(str(Path(__file__).with_name('test_prt_compiler.py')))
prt=reference['prt'];tree=reference['example']()
big='123456789012345678901234567890123456789'
predicate=prt.PythonCheck({'sans':'ans','teacher':'hidden','options':{'checker':'check'}})
node=replace(tree.nodes[1],predicate=predicate)
tree=replace(tree,nodes=(tree.nodes[0],node,*tree.nodes[2:]),arguments=('ans',),
    feedback_names=('hidden',),feedback_program='hidden:'+big)
rows=[]
nodes=list(tree.nodes)
nodes[1]=replace(nodes[1],on_true=replace(nodes[1].on_true,next_node='2'),on_false=replace(nodes[1].on_false,next_node='2'))
nodes[2]=replace(nodes[2],predicate=predicate)
two=replace(tree,nodes=tuple(nodes))
for label,model,python_nodes in [('one',tree,['1']),('two',two,['1','2'])]:
    compiled=prt.compile_tree(model)
    for bits in range(16):
        verdicts=[bool(bits&(1<<n)) for n in range(4)]
        rows.append({'id':label+'/'+str(bits),'compiled':compiled,'pythonNodes':python_nodes,
            'expectedTans':big,'verdicts':verdicts,'expected':reference['expected'](model,verdicts)})
float_model=replace(two,feedback_program='hidden:1/3.0')
rows.append({'id':'float/12','compiled':prt.compile_tree(float_model),'pythonNodes':['1','2'],
    'expectedTans':'0.3333333333333333','verdicts':[True]*4,'expected':reference['expected'](float_model,[True]*4)})
Path(sys.argv[1]).write_text(json.dumps({'rows':rows,'big':big},indent=2)+'\n')
