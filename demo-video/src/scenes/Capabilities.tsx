// The goals from docs/PRD.md section 3, plus the guardrails.
import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { C, EASE, font } from "../theme";

const ease = Easing.bezier(...EASE);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ITEMS = [
  ["Watch it live", "Who is working, what passed, what failed and why"],
  ["Every task verified", "Nothing counts as done until the checker passes it"],
  ["Keeps going", "Close the browser. Get a push when it ends"],
  ["Any specialist", "Agents invented per task, tools from a catalog you control"],
  ["Budget caps", "Cost, tasks and retries are limited. It stops cleanly"],
  ["Asks before acting", "Sending email or booking always needs your OK"],
  ["Safe with code", "Shell off by default and sandboxed. Repos work on a new branch"],
  ["Private", "Runs on your machine with your own Claude access"],
];

export const Capabilities: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: font }}>
      <div style={{ position: "absolute", top: 100, width: "100%", textAlign: "center", fontSize: 72, fontWeight: 600, letterSpacing: "-0.03em", color: C.text,
        opacity: interpolate(f, [0, 14], [0, 1], clamp) }}>
        What it does
      </div>
      <div style={{ position: "absolute", top: 260, left: 140, right: 140, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 28 }}>
        {ITEMS.map(([t, d], i) => {
          const at = 12 + i * 6;
          return (
            <div key={t} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 24, padding: "34px 30px", minHeight: 300,
              opacity: interpolate(f, [at, at + 12], [0, 1], clamp), translate: `0px ${interpolate(f, [at, at + 18], [24, 0], { ...clamp, easing: ease })}px` }}>
              <div style={{ width: 12, height: 12, borderRadius: 6, background: C.pass, marginBottom: 26 }} />
              <div style={{ fontSize: 40, fontWeight: 600, color: C.text, letterSpacing: "-0.02em" }}>{t}</div>
              <div style={{ fontSize: 28, color: C.text2, marginTop: 14, lineHeight: 1.35 }}>{d}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
