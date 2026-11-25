import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Character } from "../ui/Character";
import { C, font, mono } from "../theme";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Outro: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: font, alignItems: "center", justifyContent: "center", gap: 36, opacity: interpolate(f, [0, 14], [0, 1], clamp) }}>
      <Character color={C.orchestrator} size={140} accessory="bow" mood="happy" />
      <div style={{ fontSize: 110, fontWeight: 600, letterSpacing: "-0.04em", color: C.text }}>ChaCha PA</div>
      <div style={{ fontSize: 40, color: C.text2 }}>Built on the Claude Agent SDK</div>
      <div style={{ position: "absolute", bottom: 80, fontFamily: mono, fontSize: 22, color: C.text2, opacity: interpolate(f, [20, 36], [0, 1], clamp) }}>
        Footage recorded in demo mode: scripted agents, no model calls.
      </div>
    </AbsoluteFill>
  );
};
