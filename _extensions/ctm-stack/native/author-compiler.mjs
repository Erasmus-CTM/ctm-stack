// SPDX-License-Identifier: AGPL-3.0-or-later AND GPL-3.0-or-later
// Scoped author/CASText frontend using pinned upstream JS grammar actions.
// Produces syntax IR for the Python PRT compiler and native programs for
// author expressions; it never evaluates author maths in JavaScript.
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import maximaParser from './maxima-parser.cjs';
import castextParser from './castext-parser.cjs';
const data=JSON.parse(await fs.readFile(new URL('./compiler-data.json',import.meta.url)));
const quote=s=>'"'+String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"')+'"';
const bool=x=>x?'true':'false';
const map=pairs=>'["stack_map"'+Object.entries(pairs).map(([k,v])=>',['+quote(k)+','+v+']').join('')+']';
const scope=(locals,steps)=>'block(['+[...new Set(locals)].join(',')+'],'+steps.filter(Boolean).join(',')+')';
const ec=(expression,where)=>'_EC(errcatch('+expression+'),'+quote(where)+')';
const functions=new Set(('sqrt sin cos tan sec csc cot sinh cosh tanh sech csch coth exp log ln abs '
  +'asin acos atan asec acsc acot asinh acosh atanh asech acsch acoth cosec cosech gcd mod matrix '
  +'diff integrate sum product expand factor ratsimp cancel ev float floor ceiling round truncate '
  +'min max lcm num denom part length first second third last rest reverse append endcons cons '
  +'makelist map lambda block if listp matrixp setp numberp integerp equal is subst substinpart '
  +'set setify listify union intersection setdifference member subsetp cardinality sort '
  +'determinant rank transpose invert ident zeromatrix diag_matrix echelon charpoly '
  +'rand rand_with_step rand_with_prohib random_subset random_permutation '
  +'decimalplaces dispdp displaydp significantfigures dispsf').split(' '));
const aliases=Object.assign(Object.create(null),{ln:'log',cosec:'csc',cosech:'csch',arcsin:'asin',arccos:'acos',arctan:'atan',
  arcsec:'asec',arccot:'acot',arccsc:'acsc',arcsinh:'asinh',arccosh:'acosh',arctanh:'atanh',arcsech:'asech',arccoth:'acoth',arccsch:'acsch',
  arccosec:'acsc',arsinh:'asinh',arcosh:'acosh',artanh:'atanh',arsech:'asech',arcoth:'acoth',arcsch:'acsch'});
const constants=new Map([['e','%e'],['pi','%pi'],['Pi','%pi'],['PI','%pi'],['i','%i']]);
// These forms evaluate function arguments or syntax. They are supported only as
// audited direct calls, never as callbacks hidden in a collection or variable.
const syntaxFunctions=new Set('map sort apply subst substinpart ev at lambda block if makelist sum product'.split(' '));
const callbacks=new Set([...functions].filter(name=>!syntaxFunctions.has(name)));
function fail(where,message){throw new Error(where+': '+message);}
function safeName(value,where,allowFunction=false){
  if(typeof value!=='string'||!/^[A-Za-z][A-Za-z0-9_]*$/.test(value)||value.startsWith('ctm_')||!allowFunction&&constants.has(value)
      ||!allowFunction&&(functions.has(aliases[value]||value)||data.security[value]?.function)) fail(where,'reserved or unsupported native name '+value);
  return value;
}
function children(node){
  return Object.entries(node).filter(([k])=>!['kind','position'].includes(k)).flatMap(([,v])=>Array.isArray(v)?v:[v]).filter(v=>v&&typeof v==='object'&&typeof v.kind==='string');
}
function parse(source,where){
  if(typeof source!=='string'||source.length>20000) fail(where,'author expression exceeds its text bound');
  try{return maximaParser.parse(source);}catch(error){fail(where,'unsupported Maxima syntax: '+error.message);}
}
function analyse(node,source,where,random=false){
  const read=new Set(),calls=new Set();let replacements=[],count=0;
  const callbackSymbols='['+[...callbacks].filter(name=>random||!/^(rand|random|multiselqn)/.test(name)).map(name=>"'"+name).join(',')+']';
  function render(n){
    const start=n.position.start.offset,end=n.position.end.offset;
    let text=source.slice(start,end);
    for(const [a,b,value] of replacements.filter(([a,b])=>a>=start&&b<=end).sort((a,b)=>b[0]-a[0]))text=text.slice(0,a-start)+value+text.slice(b-start);
    return text;
  }
  function replace(n,text){
    const a=n.position.start.offset,b=n.position.end.offset;
    replacements=replacements.filter(([start,end])=>start<a||end>b);replacements.push([a,b,text]);
  }
  function callback(n){
    if(n.kind==='MPFunctionCall'&&n.name.kind==='MPIdentifier'&&n.name.value==='lambda')return;
    if(n.kind!=='MPIdentifier'||!callbacks.has(aliases[n.value]||n.value))fail(where,'unsupported native function argument: use an allowlisted function or inline lambda');
  }
  function inspect(expression,extra='true'){
    return 'local(ctm_inspect),ctm_inspect(ctm_e):=if atom(ctm_e) then true else ('
      +'if member(string(op(ctm_e)),['+[...syntaxFunctions,'ctm_inspect'].map(quote).join(',')+']) then error("unsupported syntax rewriting") else true,'
      +extra+',every(ctm_inspect,args(ctm_e))),ctm_inspect('+expression+')';
  }
  function visit(n,depth=0,asCallback=false){
    if(++count>2500||depth>100) fail(where,'author syntax exceeds its structural bound');
    if(n.kind==='MPFunctionCall'){
      if(n.name.kind!=='MPIdentifier') fail(where,'dynamic function calls require a separate capability');
      const target=aliases[n.name.value]||n.name.value;
      if(!functions.has(target)||!random&&/^(rand|random|multiselqn)/.test(target)) fail(where,'unsupported native author call '+target);
      const callbackAt=target==='map'?0:target==='sort'&&n.args.length>1?1:-1;
      if(callbackAt>=0)callback(n.args[callbackAt]);
      if(target==='lambda'){
        if(!asCallback||n.args.length!==2||n.args[0].kind!=='MPList')fail(where,'unsupported stored lambda: use an inline callback');
        for(const param of n.args[0].items){if(param.kind!=='MPIdentifier')fail(where,'unsupported lambda parameter');safeName(param.value,where);}
      }
      if(['makelist','sum','product'].includes(target)){
        if(n.args[1]?.kind!=='MPIdentifier')fail(where,'unsupported iteration variable');safeName(n.args[1].value,where);
      }
      if(target==='block'&&n.args[0]?.kind==='MPList')for(const param of n.args[0].items){if(param.kind!=='MPIdentifier')fail(where,'unsupported block binding');safeName(param.value,where);}
      if(target==='ev')for(const flag of n.args.slice(1)){
        if(flag.kind!=='MPIdentifier'||!callbacks.has(flag.value)&&!['simp','numer','nouns','noeval'].includes(flag.value))fail(where,'unsupported native evaluation flag');
      }
      if(target==='subst'){
        if(n.args.length!==3)fail(where,'unsupported substitution rules: use subst(new,old,expression)');
        if(n.args[1].kind==='MPIdentifier'&&functions.has(n.args[1].value))callback(n.args[0]);
      }
      if(target==='substinpart'&&(n.args.length<3||n.args.slice(2).some(i=>!/^\d+$/.test(source.slice(i.position.start.offset,i.position.end.offset))||Number(source.slice(i.position.start.offset,i.position.end.offset))<1)))fail(where,'unsupported operator or dynamic part substitution');
      calls.add(target);
      if(aliases[n.name.value]) replacements.push([n.name.position.start.offset,n.name.position.end.offset,target]);
      for(const [at,arg] of n.args.entries())visit(arg,depth+1,at===callbackAt);
      if(target==='subst'){
        const args=n.args.map(render);
        replace(n,'block([ctm_new:'+args[0]+',ctm_old:'+args[1]+',ctm_expr:'+args[2]+'],'
          +inspect('ctm_expr','if is(equal(op(ctm_e),ctm_old)) and not member(ctm_new,'+callbackSymbols+') then error("unsupported function substitution") else true')
          +',subst(ctm_new,ctm_old,ctm_expr))');
      }
      if(target==='substinpart'){
        const args=n.args.map(render);
        replace(n,'block([ctm_new:'+args[0]+',ctm_expr:'+args[1]+'],'+inspect('ctm_expr')+',substinpart(ctm_new,ctm_expr,'+args.slice(2).join(',')+'))');
      }
      return;
    }
    if(n.kind==='MPOperation'&&n.op.startsWith(':')) fail(where,'nested writes or function definitions require a separate capability');
    if(n.kind==='MPLoop'||n.kind==='MPEvaluationFlag'||n.kind==='MPAnnotation') fail(where,'unsupported native author control construct '+n.kind);
    if(n.kind==='MPPrefixOp'&&['?','??',"''"].includes(n.op.trim())) fail(where,'Lisp escapes and dynamic evaluation are unsupported');
    if(n.kind==='MPPrefixOp'&&n.op.trim()==="'"&&n.rhs?.kind==='MPFunctionCall'&&syntaxFunctions.has(n.rhs.name?.value))fail(where,'unsupported quoted executable syntax');
    if(n.kind==='MPIdentifier'){
      // A function passed to map is still executable authority even though it
      // is not syntactically a call. Keep callback references in the same
      // pure-function subset and reserve the compiler's own local namespace.
      if(n.value.startsWith('ctm_'))
        fail(where,'unsupported native author function or internal reference '+n.value);
      if(functions.has(aliases[n.value]||n.value)){
        if(!random&&/^(rand|random|multiselqn)/.test(n.value))fail(where,'random callbacks are only supported in question variables');
        calls.add(aliases[n.value]||n.value);
        if(aliases[n.value])replacements.push([n.position.start.offset,n.position.end.offset,aliases[n.value]]);
      }
      read.add(n.value);
      if(constants.has(n.value)) replacements.push([n.position.start.offset,n.position.end.offset,constants.get(n.value)]);
      else if(/[^\x00-\x7f]/.test(n.value)){
        let value=n.value;for(const [old,replacement] of data.replacements)value=value.split(old).join(replacement);
        if(value!==n.value) replacements.push([n.position.start.offset,n.position.end.offset,value]);
      }
    }
    if(n.kind==='MPOperation'&&['and','or'].includes(n.op)){
      const start=n.lhs.position.end.offset,end=n.rhs.position.start.offset;
      replacements.push([start,end,source.slice(start,end).replace(new RegExp('\\b'+n.op+'\\b'),'noun'+n.op)]);
    }
    if(n.kind==='MPPrefixOp'&&n.op.trim()==='not'){
      const start=n.position.start.offset,end=n.rhs.position.start.offset;
      replacements.push([start,end,source.slice(start,end).replace(/\bnot\b/,'nounnot')]);
    }
    for(const child of children(n))visit(child,depth+1);
  }
  visit(node);
  return {text:render(node),read,calls};
}
function operand(source,where,random=false){
  const root=parse(source,where),items=root.items.filter(i=>i.kind!=='MPComment');
  if(items.length!==1||items[0].kind!=='MPStatement'||items[0].flags.length)fail(where,'expected one author expression without evaluation flags');
  return analyse(items[0].expression,source,where,random);
}
function keyval(source,where,random=false){
  const root=parse(source,where),write=[],steps=[],called=new Set(),read=new Set();
  for(const [at,statement] of root.items.entries()){
    if(statement.kind==='MPComment')continue;
    const node=statement.expression;
    if(statement.kind!=='MPStatement'||statement.flags.length||node.kind!=='MPOperation'||node.op!==':'||node.lhs.kind!=='MPIdentifier')fail(where,'only scoped name:expression assignments are supported');
    const key=safeName(node.lhs.value,where);
    if(write.includes(key))fail(where,'reassigned question variable '+key);
    const rhs=analyse(node.rhs,source,where+'/'+key,random);
    rhs.calls.forEach(c=>called.add(c));rhs.read.forEach(n=>read.add(n));
    write.push(key);steps.push(ec(key+':'+rhs.text,where+'/'+at));
  }
  return {names:write,random:[...called].some(c=>/^(rand|random|multiselqn)/.test(c)),statement:steps.length?'('+steps.join(',')+',if length(%ERR)>1 then error("native author definitions failed") else true)':null,
    references:{write:Object.fromEntries(write.map(n=>[n,true])),read:Object.fromEntries([...read].map(n=>[n,true]))}};
}
function latexReplacements(){
  const r={'QMCHAR':'?','!LEFTSQ!':'\\left[','!LEFTR!':'\\left(','!RIGHTSQ!':'\\right]','!RIGHTR!':'\\right)'};
  for(const [tag,key] of [['ANDOR','equiv_ANDOR'],['SAMEROOTS','equiv_SAMEROOTS'],['MISSINGVAR','equiv_MISSINGVAR'],['ASSUMEPOSVARS','equiv_ASSUMEPOSVARS'],
    ['ASSUMEPOSREALVARS','equiv_ASSUMEPOSREALVARS'],['LET','equiv_LET'],['AND','equiv_AND'],['OR','equiv_OR'],['NOT','equiv_NOT'],['NAND','equiv_NAND'],
    ['NOR','equiv_NOR'],['XOR','equiv_XOR'],['XNOR','equiv_XNOR'],['IMPLIES','equiv_IMPLIES'],['BOOLTRUE','true'],['BOOLFALSE','false']]){
    if(typeof data.messages[key]!=='string')fail('compiler data','missing language key '+key);
    r['!'+tag+'!']=data.messages[key];
  }
  return r;
}
function mathMode(source) {
  let mode=null;
  for(const match of source.matchAll(/\\[()[\]]|\$\$?/g)) {
    let escaped=0;for(let at=match.index-1;at>=0&&source[at]==='\\';at--)escaped++;
    if(escaped%2)continue;
    const token=match[0];
    if(token==='\\('||token==='\\[')mode=token;
    else if(token==='\\)'||token==='\\]')mode=null;
    else if(mode===token)mode=null;
    else if(mode===null)mode=token;
  }
  return mode!==null;
}
export function compileIR(question){
  const variables=keyval(question.variables,'question/variables',true),inputs=question.inputs.map(i=>safeName(i.name,'input'));
  if(inputs.some(n=>variables.names.includes(n)))fail('question','question variables collide with inputs');
  const statics={},math=[],feedbackNames=new Set(),grading={},prts={};
  let staticIndex=0;
  const sourceText=JSON.stringify(question);
  let prefix;
  for(let nonce=0;nonce<10;nonce++) {
    prefix='//CTM_STATIC_'+createHash('sha256').update(String(nonce)+sourceText).digest('hex').slice(0,16)+'_';
    if(!sourceText.includes(prefix))break;
    if(nonce===9)fail('CASText','cannot allocate collision-free static markers');
  }
  const literal=value=>{
    if(value.length<20)return quote(value);
    const key=prefix+(staticIndex++)+'//';statics[key]=value;return quote(key);
  };
  function casttext(source,where,mathOutput=math,readOutput=new Set()){
    if(typeof source!=='string'||source.length>200000)fail(where,'CASText exceeds its text bound');
    if(source==='')return '""';
    let tree;try{tree=castextParser.parse(source);}catch(error){fail(where,'unsupported CASText syntax: '+error.message);}
    let count=0;
    function list(nodes){return '["%root"'+nodes.map(n=>','+visit(n)).join('')+']';}
    function visit(n){
      if(++count>3000)fail(where,'CASText exceeds its node bound');
      if(n.kind==='CTPRaw')return literal(n.value);
      if(n.kind==='CTPIOBlock'){
        if(!['input','validation','feedback'].includes(n.channel))fail(where,'unsupported IO channel '+n.channel);
        if(n.channel==='feedback'?!question.prts.some(p=>p.name===n.variable):!inputs.includes(n.variable))fail(where,'unknown IO target '+n.variable);
        return '["ioblock",'+quote(n.channel)+','+quote(n.variable)+']';
      }
      if(n.kind!=='CTPBlock')fail(where,'unsupported CASText node '+n.kind);
      if(n.name==='comment')return '""';
      if(n.name==='latex'||n.name==='raw'){
        const text=n.children.map(c=>c.value).join(''),parsed=operand(text,where+'/'+n.name),value=parsed.text;
        parsed.read.forEach(key=>readOutput.add(key));
        mathOutput.push('string('+value+')');
        if(n.name==='raw')return scope(['ctm_text'],[ec('ctm_text:'+value,where+'/raw'),'string(ctm_text)']);
        const inMath=mathMode(source.slice(0,n.position.start.offset));
        return scope(['_ct2_tmp','_ct2_simp'],['_ct2_simp:simp','_ct2_tmp:'+quote(text),ec('_ct2_tmp:'+value,where+'/latex'),
          'simp:false','_ct2_tmp:ct2_latex(_ct2_tmp,'+quote(inMath?'':'i')+',_ct2_simp)','simp:_ct2_simp','_ct2_tmp']);
      }
      if(n.name==='if'){
        const tests=Array.isArray(n.params.test)?n.params.test:[n.params.test];
        const lengths=n.params[' branch lengths']||[n.children.length];
        let index=0;const branches=lengths.map(length=>{const nodes=n.children.slice(index,index+length);index+=length;return list(nodes);});
        let expression=branches.length>tests.length?branches.at(-1):'""';
        for(let at=tests.length-1;at>=0;at--){
          const parsed=operand(tests[at].value,where+'/if'),condition=parsed.text;parsed.read.forEach(key=>readOutput.add(key));mathOutput.push('string('+condition+')');
          expression='if ('+condition+') then '+branches[at]+' else '+expression;
        }
        return expression;
      }
      fail(where,'unsupported native CASText block '+n.name);
    }
    return 'castext_simplify('+list(tree.children)+')';
  }
  const inputTeachers={};
  for(const input of question.inputs)inputTeachers[input.name]=operand(input.teacher,'input/'+input.name+'/teacher').text;
  for(const prt of question.prts){
    safeName(prt.name,'PRT',true);
    const fv=keyval(prt.feedbackvariables,'prt/'+prt.name+'/feedbackvariables');
    if(fv.names.some(n=>variables.names.includes(n)||inputs.includes(n)))fail('prt/'+prt.name,'feedback names collide with question variables or inputs');
    fv.names.forEach(n=>feedbackNames.add(n));
    const snapshots={},feedbackMath=[],required=new Set(Object.keys(fv.references.read).filter(n=>inputs.includes(n))),parsedNodes={};
    for(const node of prt.nodes){
      const where='question/prt/'+prt.name+'/n/'+node.name;
      if(!data.answerTests[node.test]&&node.test!=='PythonChecker')fail(where,'unsupported native answer test '+node.test);
      const student=operand(node.student,where+'/student');
      const teacher=node.teacher?operand(node.teacher,where+'/teacher'):{text:'""',read:new Set()};
      const options=node.options&&node.test!=='PythonChecker'?operand(node.options,where+'/options'):{text:'',read:new Set()};
      for(const part of [student,teacher,options])part.read.forEach(n=>{if(inputs.includes(n))required.add(n);});
      const value={student:student.text,teacher:teacher.text,options:options.text};
      for(const branch of ['true','false'])value[branch+'Feedback']=node[branch].feedback?.trim()
        ?casttext(' '+node[branch].feedback,where+'/'+branch+'feedback',feedbackMath,required):null;
      parsedNodes[node.name]=value;
      snapshots[node.name]=map({student:'string('+student.text+')',teacher:'string('+teacher.text+')',options:options.text?'string('+options.text+')':'""'});
    }
    prts[prt.name]={feedbackStatement:fv.statement,feedbackNames:fv.names,required:inputs.filter(n=>required.has(n)),nodes:parsedNodes,defaultPenalty:question.penalty};
    grading[prt.name]=scope([...fv.names,'simp'],['simp:'+bool(prt.autosimplify),fv.statement,'simp:false',map(snapshots)]);
    if(feedbackMath.length)math.push(scope([...fv.names,'simp'],['simp:'+bool(prt.autosimplify),fv.statement,'['+feedbackMath.join(',')+']']));
  }
  const texts={};for(const field of ['questiontext','generalfeedback','specificfeedback','questionnote'])texts[field]=casttext(question[field],'question/'+field);
  const testInputs='['+question.qtests.map(test=>map(Object.fromEntries(Object.entries(test.inputs).map(([key,value])=>{
    if(value.startsWith('CT:'))fail('question test','CASText input needs a separate capability');
    if(value.startsWith('RAW:'))return [key,quote(value.slice(4))];
    // Literal decimals are student text, including significant trailing zeros.
    // Serializing a native float would turn 17.50 into 17.5 before NumDecPlaces
    // sees its raw input. Expressions involving variables still evaluate in
    // native Maxima below; this branch performs no mathematical calculation.
    if(/^[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim()))return [key,quote(value.trim())];
    let text;try{text=operand(value,'question test').text;}catch(error){return [key,quote(value)];}
    return [key,'string('+text+')'];
  })))).join(',')+']';
  return {schema:1,variables,prts,texts,statics,inputTeachers,answerTests:data.answerTests,feedbackNames:[...feedbackNames],math:'flatten(['+math.join(',')+'])',grading:map(grading),testInputs,
    language:{schema:1,stackRevision:data.stackRevision,language:'en',messages:data.messages,latexReplacements:latexReplacements()}};
}
