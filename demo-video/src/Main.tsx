// ChaCha PA demo: the PRD's capabilities, shown with real demo-mode footage of the app.
// Each scene lasts at least as long as its voiceover (voiceover.json, from voiceover/generate.py).
// Footage scenes slow their playback to fit, and their captions stretch with them.
import { Audio } from "@remotion/media";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import React from "react";
import { staticFile } from "remotion";
import { Capabilities } from "./scenes/Capabilities";
import { Intro } from "./scenes/Intro";
import { Loop } from "./scenes/Loop";
import { Outro } from "./scenes/Outro";
import { Phone } from "./scenes/Phone";
import { sec } from "./theme";
import { Caption, Footage } from "./ui/Footage";
import voiceover from "./voiceover.json";

const T = 12;            // crossfade frames
const VO_START = 0.4;    // seconds into a scene before the voice starts
const VO_TAIL = 0.9;     // pause after the voice before the next scene

type Sfx = { at: number; file: string; volume?: number };   // at: fraction of the footage span, or seconds for non-footage
type SceneDef = {
  name: string;
  min: number;                                              // shortest the scene may be, seconds
  footage?: { src: string; start: number; span: number; captions: Caption[]; sfx?: { atSource: number; file: string; volume?: number }[] };
  render?: (seconds: number) => React.ReactNode;
  sfx?: Sfx[];
};

const DEFS: SceneDef[] = [
  { name: "Intro", min: 4.2, render: () => <Intro /> },
  { name: "Loop", min: 7, render: () => <Loop /> },
  { name: "Start a run", min: 13.4, footage: { src: "research.mp4", start: 0, span: 23.5, captions: [
    { from: 0, to: 2.6, title: "Type a task. Press start." },
    { from: 2.6, to: 6.4, title: "The orchestrator plans it and hires its own agents", sub: "It writes their instructions and picks their tools" },
    { from: 6.4, to: 10, title: "Every task has a concrete “done when”", sub: "An independent checker verifies it in the files" },
    { from: 10, to: 13.4, title: "Sent back? It retries with the feedback, then replans", sub: "The writer failed 3 times, so it hired an editor" },
  ], sfx: [{ atSource: 2.9, file: "mouse-click.wav", volume: 0.5 }] } },
  { name: "Approval", min: 8.5, footage: { src: "research.mp4", start: 23.5, span: 10.6, captions: [
    { from: 0, to: 4.2, title: "Sending an email? It asks you first.", sub: "Outward actions always need your approval" },
    { from: 4.2, to: 8.5, title: "Done only when every task passes" },
  ], sfx: [{ atSource: 27.4, file: "mouse-click.wav", volume: 0.5 }, { atSource: 29.6, file: "ding.wav", volume: 0.35 }] } },
  { name: "Build an app", min: 18.9, footage: { src: "build.mp4", start: 1, span: 30.2, captions: [
    { from: 0, to: 6.5, title: "It builds small apps, and runs the tests itself", sub: "A developer writes the code, a tester writes the tests" },
    { from: 6.5, to: 12.5, title: "The tests caught a real bug", sub: "So the fix goes to the developer, not the tester" },
    { from: 12.5, to: 18.9, title: "Every failure explained, try by try" },
  ], sfx: [{ atSource: 24.6, file: "ding.wav", volume: 0.35 }] } },
  { name: "Phone", min: 11, render: (s) => <Phone rate={32.6 / s} /> },
  { name: "History and files", min: 7.8, footage: { src: "history.mp4", start: 0, span: 7.8, captions: [
    { from: 0, to: 7.8, title: "Every run is saved", sub: "History, the files it made, and rerun with edits" },
  ] } },
  { name: "Capabilities", min: 9, render: () => <Capabilities /> },
  { name: "Outro", min: 5, render: () => <Outro /> },
];

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const vo = voiceover as Record<string, number>;

export const SCENES: [string, number, React.ReactNode][] = DEFS.map((d) => {
  const seconds = Math.max(d.min, (vo[d.name] ?? 0) + VO_START + VO_TAIL);
  let body: React.ReactNode;
  const sfx: { at: number; file: string; volume?: number }[] = [...(d.sfx ?? [])];
  if (d.footage) {
    const f = d.footage;
    const rate = f.span / seconds;
    const k = seconds / d.min;
    body = <Footage src={f.src} start={f.start} rate={rate} captions={f.captions.map((c) => ({ ...c, from: c.from * k, to: c.to * k }))} />;
    for (const s of f.sfx ?? []) sfx.push({ at: (s.atSource - f.start) / rate, file: s.file, volume: s.volume });
  } else {
    body = d.render!(seconds);
  }
  const el = (
    <>
      {body}
      {vo[d.name] !== undefined && <Audio src={staticFile(`voiceover/${slug(d.name)}.mp3`)} from={sec(VO_START)} />}
      {d.name !== "Intro" && <Audio src={staticFile("sfx/whoosh.wav")} volume={0.18} />}
      {sfx.map((s, i) => <Audio key={i} src={staticFile(`sfx/${s.file}`)} from={sec(s.at)} volume={s.volume ?? 0.4} />)}
    </>
  );
  return [d.name, sec(seconds), el];
});

export const TOTAL = SCENES.reduce((n, [, d]) => n + d, 0) - T * (SCENES.length - 1);

export const Main: React.FC = () => (
  <TransitionSeries>
    {SCENES.flatMap(([name, d, el], i) => [
      ...(i ? [<TransitionSeries.Transition key={`t${i}`} presentation={fade()} timing={linearTiming({ durationInFrames: T })} />] : []),
      <TransitionSeries.Sequence key={name} name={name} durationInFrames={d}>{el}</TransitionSeries.Sequence>,
    ])}
  </TransitionSeries>
);
