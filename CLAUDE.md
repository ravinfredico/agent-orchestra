@AGENTS.md

# Claude Code notes

Everything shared lives in AGENTS.md above. This file only adds what is specific to Claude Code.

- **Design skills:** use `ui-ux-pro-max` and `emil-design-eng` (in `.claude/skills/`) for any UI or
  motion work.
- **Design source:** the Claude Design canvas linked in `docs/DESIGN.md`. Read it with the Artifact
  tool. Ask before changing it. Don't publish to Figma until the user confirms their account.
- **Billing:** never set `ANTHROPIC_API_KEY`. Runs use the user's Claude plan login.
- **Questions:** use AskUserQuestion with concrete options for anything only the user can decide.

## Self-improvement
- When corrected, or after a mistake or gotcha, add a one-line rule to Learnings in AGENTS.md (or
  here, if it is Claude Code specific).
- After a milestone, update Status in AGENTS.md.
- Keep both files lean. Merge or delete stale rules.
- End every task by listing the doc changes you made.
- Run `/reflect` at the end of a session to review and propose updates.
