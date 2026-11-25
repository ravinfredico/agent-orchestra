// The core loop: plan, hire, assign with "done when", check, retry or replan, finish.
import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Character } from "../ui/Character";
import { C, EASE, font } from "../theme";

const ease = Easing.bezier(...EASE);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const STEPS = [
  { t: "Plan", d: "Splits the task", c: C.orchestrator, a: "bow" as const, m: "neutral" as const },
  { t: "Hire", d: "Invents the agents it needs", c: C.agents[0], a: "none" as const, m: "happy" as const },
  { t: "Assign", d: "Each task gets a “done when”", c: C.agents[1], a: "none" as const, m: "working" as const },
  { t: "Check", d: "An independent checker verifies", c: "#D4D4D4", a: "monocle" as const, m: "waiting" as const },
  { t: "Finish", d: "Only when every task passes", c: C.agents[2], a: "antenna" as const, m: "happy" as const },
];
const X0 = 170, GAP = 395;

export const Loop: React.FC = () => {
  const f = useCurrentFrame();
  const loopIn = interpolate(f, [120, 150], [0, 1], { ...clamp, easing: ease });
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: font }}>
      <div style={{ position: "absolute", top: 110, width: "100%", textAlign: "center", fontSize: 72, fontWeight: 600, letterSpacing: "-0.03em", color: C.text,
        opacity: interpolate(f, [0, 14], [0, 1], clamp) }}>
        One task in. A verified result out.
      </div>
      {STEPS.map((s, i) => {
        const at = 18 + i * 18;
        return (
          <div key={s.t} style={{ position: "absolute", top: 380, left: X0 + i * GAP - 140, width: 280, display: "flex", flexDirection: "column", alignItems: "center", gap: 18,
            opacity: interpolate(f, [at, at + 12], [0, 1], clamp), translate: `0px ${interpolate(f, [at, at + 18], [24, 0], { ...clamp, easing: ease })}px` }}>
            <Character color={s.c} size={110} accessory={s.a} mood={s.m} />
            <div style={{ fontSize: 46, fontWeight: 600, color: C.text }}>{s.t}</div>
            <div style={{ fontSize: 28, color: C.text2, textAlign: "center", lineHeight: 1.3 }}>{s.d}</div>
          </div>
        );
      })}
      {STEPS.slice(0, -1).map((_, i) => (
        <div key={i} style={{ position: "absolute", top: 432, left: X0 + i * GAP + 82, width: GAP - 164, height: 3, background: C.border,
          scale: `${interpolate(f, [30 + i * 18, 44 + i * 18], [0, 1], clamp)} 1`, transformOrigin: "left" }} />
      ))}
      <svg width="1920" height="1080" style={{ position: "absolute", inset: 0, opacity: loopIn }}>
        <path d={`M ${X0 + 3 * GAP} 720 C ${X0 + 3 * GAP} 860, ${X0 + 2 * GAP} 860, ${X0 + 2 * GAP} 720`} fill="none" stroke={C.fail} strokeWidth="4"
          strokeDasharray="600" strokeDashoffset={600 * (1 - loopIn)} />
        <path d={`M ${X0 + 2 * GAP - 12} 736 L ${X0 + 2 * GAP} 718 L ${X0 + 2 * GAP + 12} 736`} fill="none" stroke={C.fail} strokeWidth="4" />
      </svg>
      <div style={{ position: "absolute", top: 880, left: X0 + 2.5 * GAP - 400, width: 800, textAlign: "center", fontSize: 32, color: C.fail, opacity: loopIn }}>
        Sent back with feedback → retry → replan
      </div>
    </AbsoluteFill>
  );
};
