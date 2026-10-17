# Five sourced matrix-input problems

Base editor/engine: `dfc3ed55e04159be2ff13c71a163469a467d8dc9`. Five original exports were copied from official STACK revision `10d323311b7f39fb7b092dd10ce75f7d8632f525`; the manifest records exact upstream URLs, SHA-256, qtests and deployed seeds. All five Git blob hashes match upstream, and the previous 30 original exports are unchanged.

Four elementary-matrix problems run unchanged. The systems-to-matrix-equation original remains blocked by its list markup; a separately labeled teaching copy changes only its display name, removes list styling and closes the list. Its variables, inputs, PRTs and authored qtest remain identical. The original remains downloadable and its unsupported baseline is retained.

The corpus grows from 30 to 35 originals and from 73 to 82 authored qtests. The original replay baseline grows from 19 passing / one mismatch / ten blocked to 23 passing / one mismatch / eleven blocked, with 138 to 162 replayed seed/case combinations. The two existing disagreements remain unchanged. The fifth teaching copy is measured separately: its original qtest passes for all 50 deployed seeds. The four unchanged new problems pass all 24 selected seed/case combinations.

An independent Sol xhigh audit completed before PR. The review corrected a prose seed count to 313 and verified every new blob, the exact presentation-only derivative, generator coherence and preservation of the original 30 exports. Rendered source comparisons ignore only terminal line feeds introduced by Pandoc; body content and original/download hash checks remain strict.

Local validation: nine focused corpus/teaching tests passed; the fresh 35-question baseline check matched; four relevant render checks passed, and the real Worker/Pyodide corpus browser test passed in 55.02 seconds. The local full render suite stopped at an existing Windows symbolic-link privilege requirement; the full Linux suite is required in GitHub Actions.
