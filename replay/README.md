# Replay page

A public, read-only page for the portfolio. It plays back one recorded run, with play, pause, speed
and a position slider. It uses the app's own reducer and components, needs no server, and spends no
Claude usage.

- Source: `web/replay.html`, `web/src/replay/`. The run it plays is `web/src/replay/run.json`.
- Build: `cd web && npm run build:replay` writes `replay/dist/` (not committed).
- Publish: `.github/workflows/replay-pages.yml` deploys it to GitHub Pages on pushes to `main` that
  touch `web/`, or by hand from the Actions tab. Turn it on once: repo Settings → Pages → Source:
  "GitHub Actions".

## Play a different run
1. Copy a run's `runs/<id>/log.jsonl` and turn it into a JSON array:
   ```bash
   python -c "import json,sys; print(json.dumps([json.loads(l) for l in open(sys.argv[1]) if l.strip()], indent=1))" runs/<id>/log.jsonl > web/src/replay/run.json
   ```
2. Read it before publishing. The page removes machine paths and token-looking strings
   (`scrub()` in `web/src/replay/clock.ts`), but task text, results and file names are shown as they are.
3. `python scripts/make_fixtures.py` overwrites `run.json` with the demo run again.
