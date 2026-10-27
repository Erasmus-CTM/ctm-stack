#!/usr/bin/env node
// SPDX-License-Identifier: AGPL-3.0-or-later
import fs from 'node:fs/promises';
import {build} from '../_extensions/ctm-stack/native/build-runner.mjs';

// Explicit files keep author code off the shell command line. Runtime packages
// are local; this runner cannot install a browser or download an interpreter.
const args = process.argv.slice(2), options = {};
try {
  while (args.length) {
    const key = args.shift();
    if (!['--runtime', '--input', '--output', '--cache'].includes(key) || !args.length || options[key]) throw new Error('Use --runtime DIR --input JSON --output JSON [--cache DIR]');
    options[key] = args.shift();
  }
  if (!options['--runtime'] || !options['--input'] || !options['--output']) throw new Error('Use --runtime DIR --input JSON --output JSON [--cache DIR]');
  const input = await fs.readFile(options['--input']);
  if (input.length > 8 * 1024 * 1024) throw new Error('Trusted build batch exceeds 8 MiB');
  const result = await build(options['--runtime'], JSON.parse(input), {cache: options['--cache']});
  await fs.writeFile(options['--output'], JSON.stringify(result, null, 2) + '\n');
} catch (error) {
  console.error('ctm-stack native build: ' + error.message); process.exitCode = 1;
}
