---
id: short-video
title: Short videos (TikTok, Reels, Shorts)
when: Make short vertical videos end to end: trends, scripts, voiceover, render, saved to the studio for the user to post.
---
## Steps
1. In parallel (`assign_tasks`): a trend scout (`web`, haiku) writes `trends.md`; if `tiktok` is
   offered, an analyst (`tiktok`, haiku) reads recent post stats into `stats.md` with 3 lessons.
2. A script writer (`files.read`, `files.write`, sonnet) writes one file per video in `scripts/`:
   a hook that lands in 2 seconds, the voiceover text, on-screen captions, the post caption, hashtags.
   It depends on step 1 and follows the lessons and the team memory.
3. Voiceover: if `elevenlabs` is offered, a voice agent (`elevenlabs`, `files.read`, haiku) turns each
   script's voiceover text into `audio/<slug>.mp3`. Without it, skip audio and say so.
4. Render: needs `shell`. An editor (`shell`, `files.read`, `files.write`, sonnet) renders
   `videos/<slug>.mp4` at 1080x1920 with Remotion (`npx create-video@latest --blank`, then
   `npx remotion render`), using the script's captions and the audio. Without shell, skip the mp4
   and say the render is missing.
5. Studio: for every video, write `videos/<slug>.md` next to the mp4: `# <title>`, a line
   `Caption: <post caption>`, then the hashtags. The app's Studio page lists these pairs so the user
   can copy the caption, download the video and post it by hand. The user posts by hand: don't post
   or upload unless they ask in this run and `tiktok` is offered (it asks first; never retry a denial).

## Done-when templates
- trends: "trends.md lists 8 trends with a sound each and marks 3 picks"
- scripts: "scripts/ has N files; each hook is under 2 seconds of speech; each has a caption and 5 hashtags"
- voiceover: "audio/ has one mp3 per script"
- render: "videos/ has N mp4 files, each 1080x1920 and under 30 seconds"
- studio: "videos/ has a .md card per video with a title, a Caption: line and hashtags"

## Cheap checks
- `{"type": "file_count", "glob": "scripts/*.md", "min": N}` and the same for `audio/*.mp3`, `videos/*.mp4`,
  `videos/*.md`.
- With shell: `{"type": "command", "run": "ffprobe -v error -show_entries format=duration -of csv=p=0 videos/<slug>.mp4"}`
  proves the file is a real video. Leave hooks, tone and quality to the model checker.

## Pitfalls
- Rendering needs network for npm. Shell runs sandboxed: the run's allowed domains must include
  `registry.npmjs.org` (and `fonts.googleapis.com` if the template uses Google Fonts).
- ElevenLabs uses the user's credits: one voiceover per script, no retakes unless the checker fails it.
- Never reuse other creators' audio files unless the trend allows it.
- Without a TikTok token there are no stats: use the team memory (what the user said worked) instead.
