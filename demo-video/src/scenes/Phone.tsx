import { Video } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, EASE, font, mono, sec } from "../theme";

const ease = Easing.bezier(...EASE);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const POINTS = [
  ["Install it to your home screen", "Opens full screen, like an app"],
  ["Get a push when it matters", "Done, out of budget, crashed, or needs your approval"],
  ["Glance at a widget", "iPhone and Android: the running task, team and usage"],
];

export const Phone: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: font }}>
      <div style={{ position: "absolute", left: 230, top: 90, width: 430, height: 900, borderRadius: 64, background: "#000", padding: 14,
        boxShadow: "0 40px 120px rgba(0,0,0,0.7)", border: `2px solid ${C.border}`,
        translate: `0px ${interpolate(f, [0, 22], [40, 0], { ...clamp, easing: ease })}px`, opacity: interpolate(f, [0, 12], [0, 1], clamp) }}>
        <div style={{ width: 402, height: 870, borderRadius: 52, overflow: "hidden", position: "relative" }}>
          <Video src={staticFile("footage/phone.mp4")} playbackRate={2.2} muted style={{ width: 402, height: 870, objectFit: "cover" }} />
          <div style={{ position: "absolute", bottom: 14, left: 0, right: 0, textAlign: "center" }}>
            <span style={{ padding: "6px 12px", borderRadius: 999, background: "rgba(10,10,10,0.8)", color: C.text2, fontFamily: mono, fontSize: 16 }}>Demo mode · scripted run</span>
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", left: 800, top: 200, right: 120 }}>
        <div style={{ fontSize: 72, fontWeight: 600, letterSpacing: "-0.03em", color: C.text, opacity: interpolate(f, [8, 22], [0, 1], clamp) }}>
          Watch it on your phone
        </div>
        <div style={{ marginTop: 60, display: "flex", flexDirection: "column", gap: 44 }}>
          {POINTS.map(([t, d], i) => {
            const at = sec(1.2 + i * 1.4);
            return (
              <div key={t} style={{ opacity: interpolate(f, [at, at + 12], [0, 1], clamp), translate: `${interpolate(f, [at, at + 18], [24, 0], { ...clamp, easing: ease })}px 0px` }}>
                <div style={{ fontSize: 44, fontWeight: 600, color: C.text }}>{t}</div>
                <div style={{ fontSize: 30, color: C.text2, marginTop: 6 }}>{d}</div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
