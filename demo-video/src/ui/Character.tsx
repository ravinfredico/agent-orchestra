// The agent character from web/src/components/Character.tsx, as a static SVG.
import React from "react";

type Mood = "neutral" | "happy" | "working" | "sad" | "waiting" | "sleepy";
const INK = "#111111";

export const Character: React.FC<{ color: string; mood?: Mood; size?: number; accessory?: "bow" | "monocle" | "antenna" | "none" }> = ({
  color, mood = "neutral", size = 80, accessory = "none",
}) => {
  const line = { stroke: INK, strokeWidth: 2.4, fill: "none", strokeLinecap: "round" as const };
  const eyes = (dx = 0, dy = 0) => (
    <>
      <circle cx="14" cy="19" r="5" fill="#fff" /><circle cx="26" cy="19" r="5" fill="#fff" />
      <circle cx={14 + dx} cy={19 + dy} r="2.4" fill={INK} /><circle cx={26 + dx} cy={19 + dy} r="2.4" fill={INK} />
    </>
  );
  const face = {
    neutral: <>{eyes()}<path d="M16.5 29 H23.5" {...line} strokeWidth={2.2} /></>,
    working: <>{eyes(2, 1.5)}<circle cx="20" cy="29.5" r="1.8" fill={INK} /></>,
    happy: <><path d="M10 21 Q14 15.5 18 21 M22 21 Q26 15.5 30 21" {...line} /><path d="M15 27 Q20 32.5 25 27" {...line} strokeWidth={2.2} /></>,
    sad: <>{eyes(0, 1.5)}<path d="M15.5 31 Q20 27 24.5 31" {...line} strokeWidth={2.2} /></>,
    waiting: <><path d="M10 19.5 H18 M22 19.5 H30" {...line} /><path d="M16.5 29 H23.5" {...line} strokeWidth={2.2} /></>,
    sleepy: <><path d="M10 19 Q14 22.5 18 19 M22 19 Q26 22.5 30 19" {...line} /><path d="M17.5 29 H22.5" {...line} strokeWidth={2.2} /></>,
  }[mood];
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" style={{ overflow: "visible", display: "block" }}>
      <rect x="2" y="4" width="36" height="34" rx="14" fill={color} />
      {accessory === "bow" && <path d="M14 33 L20 35.5 L14 38 Z M26 33 L20 35.5 L26 38 Z" fill={INK} />}
      {accessory === "antenna" && <><path d="M20 4 V1" stroke={INK} strokeWidth="2" strokeLinecap="round" /><circle cx="20" cy="1.5" r="1.5" fill={INK} /></>}
      {face}
      {accessory === "monocle" && <><circle cx="26" cy="19.5" r="6.8" fill="none" stroke={INK} strokeWidth="1.6" /><path d="M32.5 22 L36 31" stroke={INK} strokeWidth="1.2" /></>}
    </svg>
  );
};
