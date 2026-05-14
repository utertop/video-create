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
}

export type BackgroundPickerTarget =
  | { kind: "title" }
  | { kind: "end" }
  | { kind: "section"; sectionId: string; sectionTitle: string };
