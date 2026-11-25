// A screen recording of the app in a frame, with timed captions above it.
import { Video } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, EASE, font, mono, sec } from "../theme";

export type Caption = { from: number; to: number; title: string; sub?: string };   // seconds, scene time

const ease = Easing.bezier(...EASE);

const CaptionLine: React.FC<{ c: Caption; frame: number }> = ({ c, frame }) => {
  const a = sec(c.from), b = sec(c.to);
  const opacity = interpolate(frame, [a, a + 9, b - 9, b], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(frame, [a, a + 12], [14, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
  if (frame < a || frame > b) return null;
  return (
    <div style={{ position: "absolute", inset: 0, opacity, translate: `0px ${y}px`, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
      <div style={{ fontSize: 54, fontWeight: 600, letterSpacing: "-0.03em", color: C.text, textAlign: "center" }}>{c.title}</div>
      {c.sub && <div style={{ fontSize: 30, color: C.text2, textAlign: "center" }}>{c.sub}</div>}
    </div>
  );
};

export const DemoPill: React.FC = () => (
  <div style={{ position: "absolute", right: 22, bottom: 20, padding: "8px 16px", borderRadius: 999, background: "rgba(10,10,10,0.82)",
    border: `1px solid ${C.border}`, color: C.text2, fontFamily: mono, fontSize: 20 }}>
    Demo mode · scripted run
  </div>
);

export const Footage: React.FC<{
  src: string; start: number; rate: number; captions: Caption[]; width?: number;
}> = ({ src, start, rate, captions, width = 1300 }) => {
  const frame = useCurrentFrame();
  const height = Math.round((width * 900) / 1440);
  const scale = interpolate(frame, [0, 18], [0.97, 1], { extrapolateRight: "clamp", easing: ease });
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: font }}>
      <div style={{ position: "absolute", top: 56, left: 120, right: 120, height: 140 }}>
        {captions.map((c, i) => <CaptionLine key={i} c={c} frame={frame} />)}
      </div>
      <div style={{ position: "absolute", top: 220, left: (1920 - width) / 2, width, height, borderRadius: 22, overflow: "hidden",
        border: `1px solid ${C.border}`, boxShadow: "0 40px 120px rgba(0,0,0,0.6)", scale: String(scale) }}>
        <Video src={staticFile(`footage/${src}`)} trimBefore={sec(start)} playbackRate={rate} muted style={{ width: "100%", height: "100%" }} />
        <DemoPill />
      </div>
    </AbsoluteFill>
  );
};
