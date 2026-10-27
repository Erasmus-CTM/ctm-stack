// SPDX-License-Identifier: AGPL-3.0-or-later
// Reuse pinned upstream JS grammar actions; PEG is a generation-time tool.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url), peg=require('pegjs');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const source=process.argv[2];
if(!source) throw Error('generate.mjs STACK-CHECKOUT');
const revision='33383047af39c204bf4442802a058f8b918b2b1b';
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const records=[];
async function blob(name) {
  const bytes=execFileSync('git',['-C',source,'show',revision+':'+name]);
  records.push({path:name,bytes:bytes.length,sha256:sha(bytes)});return bytes.toString('utf8');
}
const nodes=await fs.readFile(new URL('./ast.cjs',import.meta.url),'utf8');
const output=path.join(root,'_extensions/ctm-stack/native');
const check=process.argv.includes('--check');
async function write(name,body) {
  body=body.replace(/[\t ]+$/gm,'');
  const filename=path.join(output,name);
  if(check) {
    if(await fs.readFile(filename,'utf8')!==body)throw Error('Generated compiler file differs: '+name);
  } else await fs.writeFile(filename,body);
}
for(const [kind,name] of [['maxima','stack/maximaparser/autogen/parser-grammar.pegjs'],['castext','stack/cas/castext2/autogen/parser-grammar.pegjs']]) {
  let grammar=await blob(name);
  // The upstream JS actions contain TypeScript-only annotations. Erase
  // only those annotations; grammar productions/actions remain unchanged.
  grammar=grammar.replace(/\b(let\s+\w+)\s*:\s*MPNode\s*=/g,'$1 =').replace(/\((\w+) as MP(?:Operation|PrefixOp|PostfixOp)\)/g,'$1');
  const parser=peg.generate(grammar,{output:'source',format:'bare',cache:true,allowedStartRules:['Root']});
  await write(kind+'-parser.cjs','// Generated from pinned STACK grammar; GPL-3.0-or-later AND AGPL-3.0-or-later.\n'+nodes+'\nmodule.exports = '+parser+';\n');
}
const security=JSON.parse(await blob('stack/cas/security-map.json'));
const symbols=JSON.parse(await blob('stack/maximaparser/unicode/symbols-stack.json'));
const letters=JSON.parse(await blob('stack/maximaparser/unicode/letters-stack.json'));
const controller=await blob('stack/answertest/controller.class.php'),answerTests={};
const popTable=controller.slice(controller.indexOf('protected static $pops = ['));
for(const m of popTable.matchAll(/^\s*'([A-Za-z0-9_]+)'\s*=>\s*\[([^\]]+)\]/gm)) {
  const parts=m[2].split(',').map(s=>s.trim());
  if(parts.length!==5) continue;
  answerTests[m[1]]={options:parts[0]==="'optional'"?'optional':parts[0]==='true',simplify:parts[2]==='true',raw:parts[3]==='true'};
}
// Catalogue entries are data. They are generated once, never executed by the
// author tool. Exact PHP single-quoted literals only, with PHP escape rules.
const language=await blob('lang/en/qtype_stack.php'),messages={};
for(const m of language.matchAll(/^\$string\['([A-Za-z0-9_]+)'\]\s*=\s*'((?:[^'\\]|\\.)*)'\s*;/gm)) {
  if(m[1].startsWith('AT')||m[1].startsWith('irred_')||m[1].startsWith('FacForm_')||m[1]==='Subst'||m[1].startsWith('equiv_')||['true','false'].includes(m[1])) {
    messages[m[1]]=m[2].replace(/\\([\\'])/g,'$1');
  }
}
await blob('stack/prt.class.php');await blob('stack/cas/keyval.class.php');await blob('locallib.php');
for(const name of ['root.specialblock.php','latex.block.php','raw.block.php','if.block.php'])await blob('stack/cas/castext2/blocks/'+name);
await write('compiler-data.json',JSON.stringify({schema:1,stackRevision:revision,security,messages,answerTests,replacements:[...Object.entries(symbols),...Object.entries(letters)]},null,2)+'\n');
await write('compiler-provenance.json',JSON.stringify({schema:1,stackRevision:revision,generator:'pegjs@0.10.0',
  transformation:'Use upstream JavaScript grammar actions; erase TypeScript annotations; retain source text for all emitted mathematical expressions',sourceFiles:records},null,2)+'\n');
