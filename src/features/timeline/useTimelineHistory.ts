import { useCallback, useEffect, useRef, useState } from "react";
import type { V5Timeline } from "../../lib/engine";

const MAX_TIMELINE_HISTORY = 40;

interface TimelineHistoryState {
  past: V5Timeline[];
  future: V5Timeline[];
}

export function useTimelineHistory(timeline: V5Timeline | null, onTimelineChange?: (timeline: V5Timeline) => void) {
  const [history, setHistory] = useState<TimelineHistoryState>({ past: [], future: [] });
  const activeTimelineIdRef = useRef<string | null>(null);

  useEffect(() => {
    const timelineId = timeline ? timelineIdentity(timeline) : null;
    if (activeTimelineIdRef.current === timelineId) return;
    activeTimelineIdRef.current = timelineId;
    setHistory({ past: [], future: [] });
  }, [timeline]);

  const commitTimeline = useCallback((nextTimeline: V5Timeline, previousTimeline?: V5Timeline | null) => {
    if (previousTimeline) {
      setHistory((current) => ({
        past: [...current.past.slice(-(MAX_TIMELINE_HISTORY - 1)), cloneTimeline(previousTimeline)],
        future: [],
      }));
    }
    onTimelineChange?.(nextTimeline);
  }, [onTimelineChange]);

  const undo = useCallback((currentTimeline: V5Timeline | null) => {
    if (!currentTimeline) return;
    setHistory((current) => {
      const previous = current.past[current.past.length - 1];
      if (!previous) return current;
      onTimelineChange?.(markHistoryEdit(previous, "timeline_undo"));
      return {
        past: current.past.slice(0, -1),
        future: [cloneTimeline(currentTimeline), ...current.future].slice(0, MAX_TIMELINE_HISTORY),
      };
    });
  }, [onTimelineChange]);

  const redo = useCallback((currentTimeline: V5Timeline | null) => {
    if (!currentTimeline) return;
    setHistory((current) => {
      const next = current.future[0];
      if (!next) return current;
      onTimelineChange?.(markHistoryEdit(next, "timeline_redo"));
      return {
        past: [...current.past.slice(-(MAX_TIMELINE_HISTORY - 1)), cloneTimeline(currentTimeline)],
        future: current.future.slice(1),
      };
    });
  }, [onTimelineChange]);

  return {
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
    commitTimeline,
    undo,
    redo,
  };
}

function cloneTimeline(timeline: V5Timeline): V5Timeline {
  return JSON.parse(JSON.stringify(timeline)) as V5Timeline;
}

function timelineIdentity(timeline: V5Timeline): string {
  const projectId = timeline.project_ref?.project_id || "project";
  const sourcePath = timeline.source_ref?.render_plan_path || "render_plan";
  return `${projectId}:${sourcePath}:${timeline.timeline_version}`;
}

function markHistoryEdit(timeline: V5Timeline, operation: "timeline_undo" | "timeline_redo"): V5Timeline {
  return {
    ...timeline,
    metadata: {
      ...(timeline.metadata || {}),
      dirty: true,
      dirty_reason: "timeline_edit",
      last_edit_operation: operation,
      updated_at: new Date().toISOString(),
    },
  };
}
