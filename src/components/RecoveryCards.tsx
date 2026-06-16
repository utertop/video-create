import { History, RotateCcw, X } from "lucide-react";

import { shortPathName } from "./BackgroundAssetPicker";
import type { ProjectStatePayload, SessionSnapshotPayload } from "../lib/engine";
import { formatSnapshotSavedAt, parseSessionRecoveryData } from "../lib/sessionRecovery";
import type { RecentProject } from "../lib/sessionRecovery";

export function SessionRecoveryCard({
  snapshot,
  onRestore,
  onDismiss,
}: {
  snapshot: SessionSnapshotPayload;
  onRestore: (snapshot: SessionSnapshotPayload) => void;
  onDismiss: () => void;
}) {
  const restored = parseSessionRecoveryData(snapshot.data);
  if (!restored) return null;

  const draft = restored.studio;
  const summary = draft.title || (draft.inputFolder ? shortPathName(draft.inputFolder) : "未命名项目");

  return (
    <section className="session-recovery-card">
      <div className="session-recovery-head">
        <div>
          <span className="startup-health-kicker">SESSION RECOVERY</span>
          <strong>检测到上次未完成会话</strong>
        </div>
        <span className="session-recovery-badge">{formatSnapshotSavedAt(snapshot.savedAt)}</span>
      </div>
      <div className="session-recovery-body">
        <div className="session-recovery-summary">
          <strong>{summary}</strong>
          <span>{draft.inputFolder ? shortPathName(draft.inputFolder) : "未选择素材目录"} → {draft.outputFolder ? shortPathName(draft.outputFolder) : "未选择输出目录"}</span>
          <small>恢复后会带回当前阶段、渲染计划、最近日志和预检上下文，但不会自动继续中断中的渲染任务。</small>
        </div>
        <div className="session-recovery-actions">
          <button className="primary-action" type="button" onClick={() => onRestore(snapshot)}>
            <RotateCcw size={16} /> 恢复草稿
          </button>
          <button className="secondary-action" type="button" onClick={onDismiss}>
            <X size={16} /> 丢弃草稿
          </button>
        </div>
      </div>
    </section>
  );
}

export function ProjectRecoveryCard({
  project,
  snapshot,
  onRestore,
  onDismiss,
}: {
  project: RecentProject;
  snapshot: ProjectStatePayload;
  onRestore: () => void;
  onDismiss: () => void;
}) {
  const restored = parseSessionRecoveryData(snapshot.data);
  if (!restored) return null;

  const draft = restored.studio;
  const summary = draft.title || project.title || shortPathName(project.inputFolder);

  return (
    <section className="session-recovery-card">
      <div className="session-recovery-head">
        <div>
          <span className="startup-health-kicker">PROJECT AUTOSAVE</span>
          <strong>检测到上次未完成项目</strong>
        </div>
        <span className="session-recovery-badge">{formatSnapshotSavedAt(snapshot.savedAt)}</span>
      </div>
      <div className="session-recovery-body">
        <div className="session-recovery-summary">
          <strong>{summary}</strong>
          <span>{shortPathName(project.inputFolder)}{" -> "}{project.outputFolder ? shortPathName(project.outputFolder) : "未选择输出目录"}</span>
          <small>恢复后会先重新加载项目文档，再尽量带回自动保存的阶段、日志、预检和最近渲染上下文。</small>
        </div>
        <div className="session-recovery-actions">
          <button className="primary-action" type="button" onClick={onRestore}>
            <RotateCcw size={16} /> 恢复最近项目
          </button>
          <button className="secondary-action" type="button" onClick={onDismiss}>
            <X size={16} /> 稍后再说
          </button>
        </div>
      </div>
    </section>
  );
}

function formatRecentProjectTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = Date.now();
  if (now - timestamp < 24 * 60 * 60 * 1000) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString();
}

export function RecentProjectsCard({
  projects,
  onRestore,
}: {
  projects: RecentProject[];
  onRestore: (project: RecentProject) => void;
}) {
  if (projects.length === 0) return null;

  return (
    <section className="recent-projects-card">
      <div className="recent-projects-head">
        <div>
          <span className="startup-health-kicker">RECENT PROJECTS</span>
          <strong>最近项目</strong>
        </div>
        <History size={18} />
      </div>
      <div className="recent-projects-list">
        {projects.map((project) => (
          <button key={project.id} type="button" onClick={() => onRestore(project)}>
            <span>
              <strong>{project.title || shortPathName(project.inputFolder)}</strong>
              <small>{shortPathName(project.inputFolder)} → {project.outputFolder ? shortPathName(project.outputFolder) : "未选择输出目录"}</small>
            </span>
            <em>{formatRecentProjectTime(project.updatedAt)}</em>
          </button>
        ))}
      </div>
    </section>
  );
}

