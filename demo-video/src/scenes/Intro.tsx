import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Character } from "../ui/Character";
import { C, EASE, font } from "../theme";

const ease = Easing.bezier(...EASE);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Intro: React.FC = () => {
  const f = useCurrentFrame();
  const team = [C.orchestrator, ...C.agents.slice(0, 4)];
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: font, alignItems: "center", justifyContent: "center", gap: 44 }}>
      <div style={{ display: "flex", gap: 22 }}>
        {team.map((c, i) => (
          <div key={i} style={{ opacity: interpolate(f, [4 + i * 5, 16 + i * 5], [0, 1], clamp),
            translate: `0px ${interpolate(f, [4 + i * 5, 20 + i * 5], [24, 0], { ...clamp, easing: ease })}px` }}>
            <Character color={c} size={i === 0 ? 120 : 100} mood={f > 60 ? "happy" : "neutral"} accessory={i === 0 ? "bow" : i === 2 ? "antenna" : "none"} />
          </div>
        ))}
      </div>
      <div style={{ fontSize: 132, fontWeight: 600, letterSpacing: "-0.04em", color: C.text,
        opacity: interpolate(f, [24, 40], [0, 1], clamp), translate: `0px ${interpolate(f, [24, 44], [20, 0], { ...clamp, easing: ease })}px` }}>
        ChaCha PA
      </div>
      <div style={{ fontSize: 46, color: C.text2, textAlign: "center", maxWidth: 1400, lineHeight: 1.35, opacity: interpolate(f, [44, 62], [0, 1], clamp) }}>
        Give it a task. A team of AI agents plans it, does it,<br />and keeps going until every part is verified.
      </div>
    </AbsoluteFill>
  );
};
