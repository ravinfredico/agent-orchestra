# ChaCha PA demo video

A 97-second video with voiceover and sound effects, of the app's capabilities (from `docs/PRD.md`), made with [Remotion](https://www.remotion.dev).
The rendered file is `docs/media/chacha-pa-demo.mp4`.

Footage in `public/footage/` is real screen recordings of the app in demo mode: scripted agents, no
model calls. Scenes are in `src/scenes/`, the timeline and captions in `src/Main.tsx`.

## Voiceover and sound
- The narration is in `voiceover/script.json`, one line per scene. Each scene lasts at least as long as
  its line (footage slows down to fit, captions stretch with it).
- It's generated with Piper, a free offline neural voice (no account or key):
  ```bash
  pip install piper-tts
  python -m piper.download_voices en_US-lessac-high --download-dir voiceover/voices
  python voiceover/generate.py        # writes public/voiceover/*.mp3 and src/voiceover.json
  ```
  For a more natural voice, swap in a paid TTS (e.g. ElevenLabs) that writes the same mp3 files.
- Sound effects (`public/sfx/`) are from Remotion's free set at remotion.media: a soft whoosh on
  scene changes, clicks on Start and Approve, a ding when tasks pass.

## Edit and render
```bash
cd demo-video
npm install
npm run dev                 # Remotion Studio: preview and edit
npm run render              # writes out/chacha-pa-demo.mp4
cp out/chacha-pa-demo.mp4 ../docs/media/
```
The README shows `docs/media/chacha-pa-demo-preview.gif`, a 23-second highlights cut (GitHub
won't play an mp4 stored in the repo). Rebuild it after re-rendering:
```bash
cd ../docs/media
ffmpeg -y -i chacha-pa-demo.mp4 -filter_complex "[0:v]trim=1.5:5,setpts=PTS-STARTPTS[a];[0:v]trim=10:14.5,setpts=PTS-STARTPTS[b];[0:v]trim=26:32,setpts=PTS-STARTPTS[c];[0:v]trim=37.5:42,setpts=PTS-STARTPTS[d];[0:v]trim=52:60,setpts=PTS-STARTPTS[e];[0:v]trim=64.5:69,setpts=PTS-STARTPTS[f];[0:v]trim=83:87,setpts=PTS-STARTPTS[g];[a][b][c][d][e][f][g]concat=n=7:v=1:a=0,setpts=PTS/1.5,fps=12,scale=960:-1:flags=lanczos,split[x][y];[x]palettegen=max_colors=128:stats_mode=diff[p];[y][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" chacha-pa-demo-preview.gif
```
The trim times match the current scene lengths; check them if the timeline changes.

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
