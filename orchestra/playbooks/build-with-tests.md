---
id: build-with-tests
title: Build with tests
when: Write new code (script, CLI, small app, library) that must work, proven by tests.
---
## Steps
1. Needs `shell`. If shell is not offered, say so in your plan and build what you can without running it.
2. Developer (`files.read`, `files.write`, `shell`): writes the code in the files named in the task.
   Done when a concrete command runs and prints the expected output.
3. Tester (`files.read`, `files.write`, `shell`): writes tests that cover the behaviour in the task,
   including bad input, and runs them.
4. When tests fail because of a bug in the code, give the fix to the developer who owns the code, not
   the tester. Use `replaces` on the failed test task.

## Done-when templates
- code: "`<command>` exits 0 and prints <expected>"
- tests: "`pytest -q` (or the project's test command) exits 0 with at least <n> tests covering <cases>"

## Pitfalls
- A tester can't make tests pass by editing tests to match a bug. The checker runs the tests itself.
- Name the files and the command in every task, so the checker can run exactly that.
- Keep each task small enough to finish in one attempt: one module or one feature at a time.
