# ChaCha PA demo video

An 85-second video of the app's capabilities (from `docs/PRD.md`), made with [Remotion](https://www.remotion.dev).
The rendered file is `docs/media/chacha-pa-demo.mp4`.

Footage in `public/footage/` is real screen recordings of the app in demo mode: scripted agents, no
model calls. Scenes are in `src/scenes/`, the timeline and captions in `src/Main.tsx`.

## Edit and render
```bash
cd demo-video
npm install
npm run dev                 # Remotion Studio: preview and edit
npm run render              # writes out/chacha-pa-demo.mp4
cp out/chacha-pa-demo.mp4 ../docs/media/
```

## Re-record the footage (after UI changes)
```bash
python -m server --fake --port 8780 --runs-dir /tmp/demo-runs     # from the repo root, in another terminal
node demo-video/scripts/record-footage.cjs http://127.0.0.1:8780 /tmp/clips   # needs Playwright
for c in research build phone history; do
  ffmpeg -y -i /tmp/clips/$c/*.webm -c:v libx264 -crf 20 -pix_fmt yuv420p -an demo-video/public/footage/$c.mp4
done
```
Clip timings are hard-coded in `src/Main.tsx` (`start`, `rate`, caption seconds). Check them after re-recording.

Fonts: Geist and Geist Mono (SIL Open Font License), bundled in `public/fonts/` so renders work offline.
Remotion is free for individuals and teams of up to 3; see remotion.dev/license.
