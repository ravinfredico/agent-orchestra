// Tokens from docs/DESIGN.md section 5 (dark theme).
// Geist variable fonts, bundled locally (OFL, copied from the web app's @fontsource-variable packages).
import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

export const font = "Geist";
export const mono = "Geist Mono";
loadFont({ family: font, url: staticFile("fonts/geist.woff2"), weight: "100 900" });
loadFont({ family: mono, url: staticFile("fonts/geist-mono.woff2"), weight: "100 900" });

export const C = {
  bg: "#0A0A0A",
  surface: "#151515",
  surface2: "#222222",
  text: "#F5F5F5",
  text2: "#A3A3A3",
  border: "#2A2A2A",
  pass: "#4ADE80",
  fail: "#F87171",
  check: "#FBBF24",
  orchestrator: "#9D8CFF",
  agents: ["#FF8A6B", "#4FC7B8", "#F5C85C", "#B48CFF", "#7FB7FF", "#FF9FC9"],
};

export const FPS = 30;
export const sec = (s: number) => Math.round(s * FPS);
export const EASE = [0.23, 1, 0.32, 1] as const;
