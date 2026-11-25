// ChaCha PA demo: the PRD's capabilities, shown with real demo-mode footage of the app.
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import React from "react";
import { Capabilities } from "./scenes/Capabilities";
import { Intro } from "./scenes/Intro";
import { Loop } from "./scenes/Loop";
import { Outro } from "./scenes/Outro";
import { Phone } from "./scenes/Phone";
import { sec } from "./theme";
import { Footage } from "./ui/Footage";

const T = 12;   // crossfade frames

// Each entry: [name, frames, element]. Footage frames = (source seconds / rate) * fps.
export const SCENES: [string, number, React.ReactNode][] = [
  ["Intro", sec(4.2), <Intro />],
  ["Loop", sec(7), <Loop />],
  ["Start a run", sec(23.5 / 1.75), <Footage src="research.mp4" start={0} rate={1.75} captions={[
    { from: 0, to: 2.6, title: "Type a task. Press start." },
    { from: 2.6, to: 6.4, title: "The orchestrator plans it and hires its own agents", sub: "It writes their instructions and picks their tools" },
    { from: 6.4, to: 10, title: "Every task has a concrete “done when”", sub: "An independent checker verifies it in the files" },
    { from: 10, to: 13.4, title: "Sent back? It retries with the feedback, then replans", sub: "The writer failed 3 times, so it hired an editor" },
  ]} />],
  ["Approval", sec(10.6 / 1.25), <Footage src="research.mp4" start={23.5} rate={1.25} captions={[
    { from: 0, to: 4.2, title: "Sending an email? It asks you first.", sub: "Outward actions always need your approval" },
    { from: 4.2, to: 8.5, title: "Done only when every task passes" },
  ]} />],
  ["Build an app", sec(30.2 / 1.6), <Footage src="build.mp4" start={1} rate={1.6} captions={[
    { from: 0, to: 6.5, title: "It builds small apps, and runs the tests itself", sub: "A developer writes the code, a tester writes the tests" },
    { from: 6.5, to: 12.5, title: "The tests caught a real bug", sub: "So the fix goes to the developer, not the tester" },
    { from: 12.5, to: 18.9, title: "Every failure explained, try by try" },
  ]} />],
  ["Phone", sec(14.8), <Phone />],
  ["History and files", sec(7.8), <Footage src="history.mp4" start={0} rate={1} captions={[
    { from: 0, to: 7.8, title: "Every run is saved", sub: "History, the files it made, and rerun with edits" },
  ]} />],
  ["Capabilities", sec(9), <Capabilities />],
  ["Outro", sec(5), <Outro />],
];

export const TOTAL = SCENES.reduce((n, [, d]) => n + d, 0) - T * (SCENES.length - 1);

export const Main: React.FC = () => (
  <TransitionSeries>
    {SCENES.flatMap(([name, d, el], i) => [
      ...(i ? [<TransitionSeries.Transition key={`t${i}`} presentation={fade()} timing={linearTiming({ durationInFrames: T })} />] : []),
      <TransitionSeries.Sequence key={name} name={name} durationInFrames={d}>{el}</TransitionSeries.Sequence>,
    ])}
  </TransitionSeries>
);
