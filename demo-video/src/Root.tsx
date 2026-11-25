import React from "react";
import { Composition, Folder } from "remotion";
import { Main, SCENES, TOTAL } from "./Main";
import { FPS } from "./theme";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="ChaChaDemo" component={Main} width={1920} height={1080} fps={FPS} durationInFrames={TOTAL} />
    <Folder name="Scenes">
      {SCENES.map(([name, d, el]) => (
        <Composition key={name} id={name.replace(/\s+/g, "-")} component={() => <>{el}</>} width={1920} height={1080} fps={FPS} durationInFrames={d} />
      ))}
    </Folder>
  </>
);
