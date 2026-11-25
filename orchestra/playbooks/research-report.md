---
id: research-report
title: Research report
when: Find facts on the web and write them up as a report, comparison or brief with sources.
---
## Steps
1. Research: one agent per source cluster (or one researcher for small topics) with `web` and
   `files.write`. Each item gets its own file in `research/`, with the facts and the URL for every claim.
2. Analyse (if the task compares things): an analyst with `files.read` and `files.write` turns the
   notes into tables in `analysis/`.
3. Write: a writer with `files.read` (which includes Grep search) and `files.write` assembles the final
   file named in the task. It must copy sources from `research/`, not invent or drop them.
4. Optional last pass: an editor checks that every claim in the report has a source from `research/`.

## Done-when templates
- research: "research/ has one file per <item> (<list>), each with <fields> and at least <n> source URLs"
- analysis: "analysis/<file>.md has a table covering every <item> with columns <cols>"
- report: "<file> has <sections>, the table from analysis/, and a Sources section listing every URL
  from research/ (at least <n>)"

## Pitfalls
- Writers without file search drop sources. Give the writer Grep (`files.read`), and say "list every
  URL found in research/".
- Vague counts fail checks. Always say how many items, sections and sources.
- Do not let two parallel researchers write the same file. Name files per item.
