"""Small independently specified matrix truths for the native H1 boundary."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def matrices(destination):
    def write(filename,title,variables,teacher,tans,checker,options,tests):
        root=ET.Element('quiz');q=ET.SubElement(root,'question',type='stack')
        def text(parent,name,value):ET.SubElement(ET.SubElement(parent,name),'text').text=value
        text(q,'name',title);text(q,'questionvariables',variables)
        text(q,'questiontext','<p>[[input:ans]] [[validation:ans]] [[feedback:result]]</p>')
        ET.SubElement(q,'questionsimplify').text='1';ET.SubElement(q,'penalty').text='.1'
        inp=ET.SubElement(q,'input')
        for key,value in {'name':'ans','type':'matrix','tans':teacher,'strictsyntax':'1','insertstars':'0','checkanswertype':'1'}.items():ET.SubElement(inp,key).text=value
        matrix=ET.SubElement(inp,'matrix')
        if filename=='basis.xml':
            ET.SubElement(matrix,'rows',initial='3',min='3',max='3',resizable='0')
            ET.SubElement(matrix,'cols',initial='1',min='1',max='2',resizable='1')
        else:
            ET.SubElement(matrix,'rows',initial='2',min='2',max='2',resizable='0')
            ET.SubElement(matrix,'cols',initial='2',min='2',max='2',resizable='0')
        prt=ET.SubElement(q,'prt')
        for key,value in {'name':'result','value':'1','autosimplify':'1'}.items():ET.SubElement(prt,key).text=value
        node=ET.SubElement(prt,'node')
        for key,value in {'name':'0','answertest':'PythonChecker','sans':'ans','tans':tans,
                          'testoptions':json.dumps({'checker':checker,'options':options})}.items():ET.SubElement(node,key).text=value
        for side,score in [('true','1'),('false','0')]:
            for field,value in {'scoremode':'=','score':score,'nextnode':'-1','answernote':'result-'+('T' if score=='1' else 'F')}.items():ET.SubElement(node,side+field).text=value
        for index,(answer,score) in enumerate(tests,1):
            test=ET.SubElement(q,'qtest');ET.SubElement(test,'testcase').text=str(index)
            incoming=ET.SubElement(test,'testinput');ET.SubElement(incoming,'name').text='ans';ET.SubElement(incoming,'value').text=answer
            expected=ET.SubElement(test,'expected')
            for field,value in {'name':'result','expectedscore':str(score),'expectedpenalty':'0' if score else '.1',
                                'expectedanswernote':'result-T' if score else 'result-F'}.items():ET.SubElement(expected,field).text=value
        path=Path(destination)/filename;ET.ElementTree(root).write(path,encoding='unicode');return path
    basis=write('basis.xml','Native nullspace basis','M:matrix([1,0,0],[0,1,0],[0,0,0]);B:matrix([0],[0],[1]);',
        'B','M','basis',{'space':'nullspace'},[('B',1),('matrix([1],[0],[0])',0),('matrix([0,0],[0,0],[1,2])',0)])
    hpd=write('hpd.xml','Native Hermitian positivity','M:matrix([2,i],[-i,2]);','M','true','is_hpd',{},
        [('M',1),('matrix([1,2*i],[-2*i,1])',0)])
    return [basis,hpd]
