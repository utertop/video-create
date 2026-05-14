import { FolderOpen, ImagePlus } from "lucide-react";
import { open } from "@tauri-apps/plugin-dialog";

export function FolderSelector({
  inputFolder,
  setInputFolder,
}: {
  inputFolder: string | null;
  setInputFolder: (folder: string | null) => void;
}) {
  async function handleSelect() {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
      });
      if (selected && typeof selected === "string") {
        setInputFolder(selected);
      }
    } catch (error) {
      console.error("Failed to select folder:", error);
    }
  }

  return (
    <div className="folder-selector">
      {inputFolder ? (
        <div className="selected-folder">
          <FolderOpen size={24} />
          <div className="folder-info">
            <strong>已选择素材目录</strong>
            <span className="folder-path" title={inputFolder}>{inputFolder}</span>
          </div>
          <button className="folder-change-btn" onClick={handleSelect}>更改目录</button>
        </div>
      ) : (
        <div className="drop-zone" onClick={handleSelect}>
          <ImagePlus size={30} />
          <strong>点击选择照片/视频所在的文件夹</strong>
          <span>脚本将自动扫描该目录下的素材</span>
        </div>
      )}
    </div>
  );
}

export function OutputFolderSelector({
  disabled,
  invalid,
  outputFolder,
  setOutputFolder,
}: {
  disabled: boolean;
  invalid: boolean;
  outputFolder: string | null;
  setOutputFolder: (folder: string | null) => void;
}) {
  async function handleSelect() {
    if (disabled) return;

    try {
      const selected = await open({
        directory: true,
        multiple: false,
      });
      if (selected && typeof selected === "string") {
        setOutputFolder(selected);
      }
    } catch (error) {
      console.error("Failed to select output folder:", error);
    }
  }

  return (
    <label className={invalid ? "folder-field invalid" : "folder-field"}>
      输出目录
      <div className="folder-input-row">
        <input
          readOnly
          disabled={disabled}
          title={outputFolder || ""}
          value={outputFolder || (disabled ? "请先选择素材目录" : "请选择输出目录")}
        />
        <button disabled={disabled} type="button" onClick={handleSelect}>
          选择目录
        </button>
      </div>
    </label>
  );
}
