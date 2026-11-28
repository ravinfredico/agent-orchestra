@AGENTS.md

# Claude Code notes

Everything shared lives in AGENTS.md above. This file only adds what is specific to Claude Code.

- **Design skills:** use `ui-ux-pro-max` and `emil-design-eng` (in `.claude/skills/`) for any UI or
  motion work.
- **pstack** (Lauren Tan's skills, Claude Code port, enabled in `.claude/settings.json`): use
  `pstack:poteto-mode` for multi-file, design or debugging work, as its session hook says. When pstack
  and AGENTS.md disagree, AGENTS.md wins. Our `/reflect` command is separate from `pstack:reflect`.
- **Design source:** the Claude Design canvas linked in `docs/DESIGN.md`. Read it with the Artifact
  tool. Ask before changing it. Don't publish to Figma until the user confirms their account.
  To add a sheet, write `project/<name>.dc.html` and add its entry to `boards` and `order` in
  `project/canvas.json`, placed in free space. Publish both in one Artifact call with `root`.
- **Cloud sessions:** the container starts without dependencies. Run `pip install -r requirements.txt`
  and `cd web && npm install` before the first test run.
- **Live runs from the cloud:** the container's `claude` CLI is signed in, so real runs work there
  (`python -m server --port 8001`, own `--runs-dir`). Use the Cheap preset and `max_cost` 1.
- **Billing:** never set `ANTHROPIC_API_KEY`. Runs use the user's Claude plan login.
- **Questions:** use AskUserQuestion with concrete options for anything only the user can decide.

## Self-improvement
- When corrected, or after a mistake or gotcha, add a one-line rule to Learnings in AGENTS.md (or
  here, if it is Claude Code specific).
- After a milestone, update Status in AGENTS.md.
- Keep both files lean. Merge or delete stale rules.
- End every task by listing the doc changes you made.
- Run `/reflect` at the end of a session to review and propose updates.
