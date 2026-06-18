import { create } from "zustand";
import {
  AspectRatio,
  EditStrategy,
  MusicFitStrategy,
  MusicMode,
  MusicPlaylistMode,
  PerformanceMode,
  Quality,
  RenderEngine,
  V5ChapterBackgroundMode,
  V5MediaLibrary,
  V5RenderPlan,
  V5StoryBlueprint,
  V5Timeline,
  V5TimelinePreviewManifest,
  V5TitleStyle,
} from "../lib/engine";

export interface StudioState {
  inputFolder: string | null;
  outputFolder: string | null;
  title: string;
  titleSubtitle: string;
  endText: string;
  titleStyle: V5TitleStyle;
  endStyle: V5TitleStyle;
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
  editStrategy: EditStrategy;
  performanceMode: PerformanceMode;
  renderEngine: RenderEngine;
  musicMode: MusicMode;
  musicPath: string | null;
  musicPlaylistMode: MusicPlaylistMode;
  musicPlaylistPaths: string[];
  musicFitStrategy: MusicFitStrategy;
  bgmVolume: number;
  sourceAudioVolume: number;
  keepSourceAudio: boolean;
  autoDucking: boolean;
  musicFadeInSeconds: number;
  musicFadeOutSeconds: number;
  isDryRun: boolean;
  telemetryEnabled: boolean;

  v5Stage: "INPUT" | "BLUEPRINT" | "RENDER";
  v5Library: V5MediaLibrary | null;
  v5Blueprint: V5StoryBlueprint | null;
  v5RenderPlan: V5RenderPlan | null;
  v5Timeline: V5Timeline | null;
  v5TimelinePreviewManifest: V5TimelinePreviewManifest | null;

  setInputFolder: (folder: string | null) => void;
  setOutputFolder: (folder: string | null) => void;
  patch: (data: Partial<StudioState>) => void;
}

export type StudioAppState = StudioState;

export const selectStudioAppState = (state: StudioState): StudioAppState => ({
  inputFolder: state.inputFolder,
  outputFolder: state.outputFolder,
  title: state.title,
  titleSubtitle: state.titleSubtitle,
  endText: state.endText,
  titleStyle: state.titleStyle,
  endStyle: state.endStyle,
  titleBackgroundPath: state.titleBackgroundPath,
  endBackgroundPath: state.endBackgroundPath,
  chapterBackgroundMode: state.chapterBackgroundMode,
  outputName: state.outputName,
  aspectRatio: state.aspectRatio,
  quality: state.quality,
  watermark: state.watermark,
  recursive: state.recursive,
  chaptersFromDirs: state.chaptersFromDirs,
  cover: state.cover,
  editStrategy: state.editStrategy,
  performanceMode: state.performanceMode,
  renderEngine: state.renderEngine,
  musicMode: state.musicMode,
  musicPath: state.musicPath,
  musicPlaylistMode: state.musicPlaylistMode,
  musicPlaylistPaths: state.musicPlaylistPaths,
  musicFitStrategy: state.musicFitStrategy,
  bgmVolume: state.bgmVolume,
  sourceAudioVolume: state.sourceAudioVolume,
  keepSourceAudio: state.keepSourceAudio,
  autoDucking: state.autoDucking,
  musicFadeInSeconds: state.musicFadeInSeconds,
  musicFadeOutSeconds: state.musicFadeOutSeconds,
  isDryRun: state.isDryRun,
  telemetryEnabled: state.telemetryEnabled,
  v5Stage: state.v5Stage,
  v5Library: state.v5Library,
  v5Blueprint: state.v5Blueprint,
  v5RenderPlan: state.v5RenderPlan,
  v5Timeline: state.v5Timeline,
  v5TimelinePreviewManifest: state.v5TimelinePreviewManifest,
  setInputFolder: state.setInputFolder,
  setOutputFolder: state.setOutputFolder,
  patch: state.patch,
});

export const useStudio = create<StudioState>((set) => ({
  inputFolder: null,
  outputFolder: null,
  title: "福建旅行混剪",
  titleSubtitle: "Travel Video",
  endText: "To be continued!",
  titleStyle: { preset: "cinematic_bold", motion: "cinematic_reveal" },
  endStyle: { preset: "film_subtitle", motion: "static_hold" },
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
  editStrategy: "smart_director",
  performanceMode: "balanced",
  renderEngine: "auto",
  musicMode: "off",
  musicPath: null,
  musicPlaylistMode: "single",
  musicPlaylistPaths: [],
  musicFitStrategy: "auto",
  bgmVolume: 0.28,
  sourceAudioVolume: 1.0,
  keepSourceAudio: true,
  autoDucking: true,
  musicFadeInSeconds: 1.5,
  musicFadeOutSeconds: 3.0,
  isDryRun: false,
  telemetryEnabled: false,

  v5Stage: "INPUT",
  v5Library: null,
  v5Blueprint: null,
  v5RenderPlan: null,
  v5Timeline: null,
  v5TimelinePreviewManifest: null,

  setInputFolder: (folder) => set({
    inputFolder: folder,
    v5Stage: "INPUT",
    v5Library: null,
    v5Blueprint: null,
    v5RenderPlan: null,
    v5Timeline: null,
    v5TimelinePreviewManifest: null,
    titleBackgroundPath: null,
    endBackgroundPath: null,
  }),
  setOutputFolder: (folder) => set({ outputFolder: folder }),
  patch: (state) => set(state),
}));
