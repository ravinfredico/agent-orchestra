---
id: repo-change
title: Change an existing repo
when: Add a feature or fix a bug in an existing codebase (repo mode), keeping its tests green.
---
## Steps
1. Explore first: an explorer (`files.read`, plus `shell` if offered) writes `.agents/notes/repo.md`:
   layout, conventions, how to run the tests, and the files the change will touch. Nothing is changed yet.
2. Change: an engineer (`files.read`, `files.write`, `shell`) makes the smallest change that does
   the task, following the conventions in the notes. New behaviour gets a test.
3. Verify: the engineer runs the full test suite. If something unrelated was already failing before
   the change, say so in the report instead of "fixing" it.

## Done-when templates
- explore: ".agents/notes/repo.md names the test command, the main modules, and the files to change"
- change: "<feature> works as described, a new test covers it, and `<test command>` exits 0"

## Pitfalls
- Do not rewrite or reformat files the task does not need. Small diffs are easier to review.
- Do not add new dependencies unless the task asks for them.
- The repo is on a fresh branch. Never commit, push, or switch branches.
