export interface VideoEvent {
  type?: string;
  message?: string;
  phase?: string;
  percent?: number;
  current?: number;
  total?: number;
  ok?: boolean;
  output_path?: string;
  output_dir?: string;
  artifact?: string;
  path?: string;
  item_kind?: string;
  rel_path?: string;
  display_name?: string;
  width?: number;
  height?: number;
  duration?: number;
  thumbnail?: string;
  error?: string;
  chapter?: string;
  mtime?: number;
  eligible?: number;
  hit?: number;
  created?: number;
  fallback?: number;
  overlay_eligible?: number;
  overlay_hit?: number;
  overlay_created?: number;
  saved_live_composes?: number;
  saved_render_seconds?: number;
  saved_live_fits?: number;
}

export interface PhotoSegmentCacheStats {
  eligible: number;
  hit: number;
  created: number;
  fallback: number;
  overlay_eligible: number;
  overlay_hit: number;
  overlay_created: number;
  saved_live_composes: number;
  saved_render_seconds: number;
}

export interface VideoSegmentCacheStats {
  eligible: number;
  hit: number;
  created: number;
  fallback: number;
  saved_live_fits: number;
  saved_render_seconds: number;
}

export type BackgroundPickerTarget =
  | { kind: "title" }
  | { kind: "end" }
  | { kind: "section"; sectionId: string; sectionTitle: string };
