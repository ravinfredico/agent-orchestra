---
id: general
title: General
when: Anything that doesn't fit another playbook. Plan it from scratch.
---
## Steps
1. Split the task into 2 to 5 subtasks, each producing a file a checker can inspect.
2. Create one specialist per kind of work, with the fewest tools that do the job.
3. Run independent subtasks first, then the ones that build on them, then one task that assembles
   the final deliverable.

## Done-when templates
- "<file> exists and contains <concrete things a reader can count or find>"

## Pitfalls
- If a done_when can't be checked by reading files (or running a command with shell), rewrite it
  until it can.
- If a task fails twice for the same reason, change the approach (tools, agent, split), not just
  the wording.
