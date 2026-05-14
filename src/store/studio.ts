import { create } from "zustand";
import {
  AspectRatio,
  Quality,
  RenderEngine,
  V5ChapterBackgroundMode,
  V5MediaLibrary,
  V5RenderPlan,
  V5StoryBlueprint,
} from "../lib/engine";

export interface StudioState {
  inputFolder: string | null;
  outputFolder: string | null;
  title: string;
  titleSubtitle: string;
  endText: string;
  titleBackgroundPath: string | null;
  endBackgroundPath: string | null;
  chapterBackgroundMode: V5ChapterBackgroundMode;
  outputName: string;
  aspectRatio: AspectRatio;
  quality: Quality;
  watermark: string;
  recursive: boolean;
  chaptersFromDirs: boolean;
  cover: boolean;
  renderEngine: RenderEngine;
  isDryRun: boolean;

  v5Stage: "INPUT" | "BLUEPRINT" | "RENDER";
  v5Library: V5MediaLibrary | null;
  v5Blueprint: V5StoryBlueprint | null;
  v5RenderPlan: V5RenderPlan | null;

  setInputFolder: (folder: string | null) => void;
  setOutputFolder: (folder: string | null) => void;
  patch: (data: Partial<StudioState>) => void;
}

export const useStudio = create<StudioState>((set) => ({
  inputFolder: null,
  outputFolder: null,
  title: "福建旅行混剪",
  titleSubtitle: "Travel Video",
  endText: "To be continued!",
  titleBackgroundPath: null,
  endBackgroundPath: null,
  chapterBackgroundMode: "auto_bridge",
  outputName: "travel_video",
  aspectRatio: "16:9",
  quality: "high",
  watermark: "utertop",
  recursive: true,
  chaptersFromDirs: true,
  cover: true,
  renderEngine: "auto",
  isDryRun: false,

  v5Stage: "INPUT",
  v5Library: null,
  v5Blueprint: null,
  v5RenderPlan: null,

  setInputFolder: (folder) => set({
    inputFolder: folder,
    v5Stage: "INPUT",
    v5Library: null,
    v5Blueprint: null,
    v5RenderPlan: null,
    titleBackgroundPath: null,
    endBackgroundPath: null,
  }),
  setOutputFolder: (folder) => set({ outputFolder: folder }),
  patch: (state) => set(state),
}));
