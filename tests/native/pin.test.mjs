// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {createRequire} from 'node:module';
const directory=new URL('../../_extensions/ctm-stack/native/',import.meta.url);
const pin=JSON.parse(await fs.readFile(new URL('stack-pin.json',directory))).revision;
const context={};vm.createContext(context);
for(const file of ['stack-pin.js','feedback.js','question-engine.js'])
  vm.runInContext(await fs.readFile(new URL(file,directory),'utf8'),context,{filename:file});
assert.equal(context.CTMStackRevision,pin);
assert.equal(typeof context.NativeFeedback.describe,'function');
assert.equal(typeof context.CTMMaximaQuestions.Engine,'function');
assert.equal(createRequire(import.meta.url)('../../_extensions/ctm-stack/native/stack-pin.js'),pin);
console.log('Single STACK pin loads in Node and classic browser worker scripts');
