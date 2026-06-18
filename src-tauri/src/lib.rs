use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{hash_map::DefaultHasher, HashMap};
use std::hash::{Hash, Hasher};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Clone, Default)]
struct JobManager {
    current: Arc<Mutex<Option<ActiveJob>>>,
    queued: Arc<Mutex<Vec<QueuedJob>>>,
    queue_lock: Arc<Mutex<()>>,
    worker: Arc<Mutex<Option<WorkerProcess>>>,
}

#[derive(Clone)]
struct ActiveJob {
    id: String,
    pid: u32,
    cancelled: Arc<AtomicBool>,
}

#[derive(Clone)]
struct QueuedJob {
    id: String,
    cancelled: Arc<AtomicBool>,
}

struct WorkerProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum WorkerLaunchKind {
    BundledExecutable,
    PythonScript,
}

#[derive(Debug)]
struct WorkerLaunchSpec {
    program: PathBuf,
    args: Vec<String>,
    working_dir: Option<PathBuf>,
    kind: WorkerLaunchKind,
}

const CURRENT_V5_SCHEMA_VERSION: &str = "5.5";
const CURRENT_TIMELINE_VERSION: &str = "v1";
const TELEMETRY_SCHEMA_VERSION: &str = "1";
const TELEMETRY_CONSENT_VERSION: &str = "telemetry-consent-2026-05-v1";
const MAX_PENDING_REMOTE_EVENTS: usize = 50;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GenerateVideoResult {
    ok: bool,
    code: Option<String>,
    message: String,
    command_preview: String,
    output_path: Option<String>,
    output_dir: Option<String>,
    cancelled: bool,
    is_dry_run: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct StartupCheckItem {
    id: String,
    label: String,
    ok: bool,
    code: Option<String>,
    message: String,
    detail: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct StartupDiagnostics {
    ok: bool,
    code: Option<String>,
    summary: String,
    checks: Vec<StartupCheckItem>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProjectDocumentsLoadResult {
    project_dir: String,
    migrated: bool,
    migration_notes: Vec<String>,
    library: Option<Value>,
    blueprint: Option<Value>,
    render_plan: Option<Value>,
    timeline: Option<Value>,
    timeline_preview_manifest: Option<Value>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct BuildReportSummary {
    report_path: String,
    manifest_path: Option<String>,
    build_report_version: Option<String>,
    timeline_summary: Option<Value>,
    route_summary: Option<Value>,
    fallback_summary: Option<Value>,
    cache_summary: Option<Value>,
    recompute_summary: Option<Value>,
    performance_summary: Option<Value>,
    quality_summary: Option<Value>,
    recovery_summary: Option<Value>,
    migration_notes: Vec<String>,
    report_suggestions: Option<Value>,
    status: Option<String>,
    render_intent: Option<String>,
    render_mode: Option<String>,
    failed_stage: Option<String>,
    output_path: Option<String>,
    selected_backend: Option<String>,
    actual_backend: Option<String>,
    backend_reason: Option<String>,
    fallback_chain: Vec<String>,
    fallback_used: Option<String>,
    fallback_reason: Option<String>,
    fallback_applied: bool,
    chunk_count: Option<usize>,
    segment_fast_path_rate: Option<f64>,
    chunk_fast_path_rate: Option<f64>,
    segment_route_difference_count: usize,
    segment_route_difference_rate: Option<f64>,
    created_at: Option<String>,
    resumable: bool,
    resumed_from_manifest: bool,
    reused_chunk_count: usize,
    completed_chunk_count: usize,
    failed_chunk_count: usize,
    reported_chunk_count: usize,
    failed_chunk: Option<String>,
    failure_code: Option<String>,
    failure_message: Option<String>,
    retryable: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct TelemetryCountEntry {
    key: String,
    count: u64,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct TelemetrySummary {
    telemetry_enabled: bool,
    current_consent_version: String,
    consent_accepted_version: Option<String>,
    remote_upload_enabled: bool,
    remote_endpoint_configured: bool,
    remote_endpoint: Option<String>,
    remote_endpoint_host: Option<String>,
    pending_remote_events: u64,
    last_remote_upload_at: Option<String>,
    last_remote_upload_error: Option<String>,
    sessions_started: u64,
    sessions_completed_cleanly: u64,
    sessions_crashed: u64,
    crash_free_session_rate: f64,
    first_export_sessions: u64,
    first_export_successes: u64,
    first_export_success_rate: f64,
    render_attempts: u64,
    render_successes: u64,
    render_failures: u64,
    recovery_resumable_events: u64,
    recovery_retryable_events: u64,
    top_error_codes: Vec<TelemetryCountEntry>,
    top_support_queues: Vec<TelemetryCountEntry>,
    top_tags: Vec<TelemetryCountEntry>,
    top_severities: Vec<TelemetryCountEntry>,
    recent_events: Vec<TelemetryEventRecord>,
    last_updated_at: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct TelemetrySessionStartResponse {
    session_id: Option<String>,
    telemetry_enabled: bool,
    previous_session_recovered_as_crash: bool,
    summary: TelemetrySummary,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct TelemetryEventRecord {
    session_id: Option<String>,
    event_type: String,
    timestamp: String,
    success: Option<bool>,
    error_code: Option<String>,
    support_queue: Option<String>,
    severity: Option<String>,
    tags: Vec<String>,
    recovery_resumable: bool,
    recovery_retryable: bool,
    recovery_completed_chunks: u64,
    recovery_reused_chunks: u64,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct TelemetryRemoteEnvelope {
    id: String,
    queued_at: String,
    app_version: String,
    consent_version: String,
    event: TelemetryEventRecord,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct TelemetrySettingsPayload {
    consent_accepted_version: Option<String>,
    remote_upload_enabled: Option<bool>,
    remote_endpoint: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
#[serde(default)]
struct TelemetryRemoteConfig {
    consent_accepted_version: Option<String>,
    remote_upload_enabled: bool,
    remote_endpoint: Option<String>,
    pending_events: Vec<TelemetryRemoteEnvelope>,
    last_upload_at: Option<String>,
    last_upload_error: Option<String>,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct TelemetryEventPayload {
    session_id: Option<String>,
    event_type: String,
    timestamp: Option<String>,
    success: Option<bool>,
    first_export: Option<bool>,
    error_code: Option<String>,
    support_queue: Option<String>,
    severity: Option<String>,
    tags: Option<Vec<String>>,
    recovery_resumable: Option<bool>,
    recovery_retryable: Option<bool>,
    recovery_completed_chunks: Option<u64>,
    recovery_reused_chunks: Option<u64>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct ActiveTelemetrySession {
    session_id: String,
    started_at: String,
    telemetry_enabled: bool,
    first_export_recorded: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct TelemetryAggregate {
    sessions_started: u64,
    sessions_completed_cleanly: u64,
    sessions_crashed: u64,
    first_export_sessions: u64,
    first_export_successes: u64,
    render_attempts: u64,
    render_successes: u64,
    render_failures: u64,
    recovery_resumable_events: u64,
    recovery_retryable_events: u64,
    error_codes: HashMap<String, u64>,
    support_queues: HashMap<String, u64>,
    tags: HashMap<String, u64>,
    severities: HashMap<String, u64>,
    last_updated_at: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
#[serde(default)]
struct TelemetryStore {
    schema_version: String,
    preference_enabled: bool,
    active_session: Option<ActiveTelemetrySession>,
    remote: TelemetryRemoteConfig,
    summary: TelemetryAggregate,
    recent_events: Vec<TelemetryEventRecord>,
}

impl Default for TelemetryStore {
    fn default() -> Self {
        Self {
            schema_version: TELEMETRY_SCHEMA_VERSION.to_string(),
            preference_enabled: false,
            active_session: None,
            remote: TelemetryRemoteConfig::default(),
            summary: TelemetryAggregate::default(),
            recent_events: Vec::new(),
        }
    }
}

#[tauri::command]
async fn startup_self_check(app: AppHandle) -> Result<StartupDiagnostics, String> {
    tauri::async_runtime::spawn_blocking(move || startup_self_check_blocking(&app))
        .await
        .map_err(|e| coded_error("E_STARTUP_INTERNAL", format!("startup self-check failed unexpectedly: {}", e)))
        ?
}

#[tauri::command]
async fn preflight_render_v5(
    input_folder: String,
    output_dir: String,
    plan_path: String,
    output_path: String,
) -> Result<StartupDiagnostics, String> {
    tauri::async_runtime::spawn_blocking(move || {
        preflight_render_v5_blocking(input_folder, output_dir, plan_path, output_path)
    })
    .await
    .map_err(|e| coded_error("E_PREFLIGHT_INTERNAL", format!("render preflight failed unexpectedly: {}", e)))?
}

#[tauri::command]
async fn save_session_snapshot(app: AppHandle, snapshot_json: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let path = session_snapshot_path(&app)?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("无法创建会话快照目录 {}: {}", parent.display(), e))?;
        }
        std::fs::write(&path, snapshot_json)
            .map_err(|e| format!("无法保存会话快照 {}: {}", path.display(), e))
    })
    .await
    .map_err(|e| format!("保存会话快照后台任务异常: {}", e))?
}

#[tauri::command]
async fn load_session_snapshot(app: AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let path = session_snapshot_path(&app)?;
        if !path.is_file() {
            return Ok(None);
        }
        let content = std::fs::read_to_string(&path)
            .map_err(|e| format!("无法读取会话快照 {}: {}", path.display(), e))?;
        Ok(Some(content))
    })
    .await
    .map_err(|e| format!("读取会话快照后台任务异常: {}", e))?
}

#[tauri::command]
async fn clear_session_snapshot(app: AppHandle) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let path = session_snapshot_path(&app)?;
        if path.exists() {
            std::fs::remove_file(&path)
                .map_err(|e| format!("无法删除会话快照 {}: {}", path.display(), e))?;
        }
        Ok(())
    })
    .await
    .map_err(|e| format!("清理会话快照后台任务异常: {}", e))?
}

#[tauri::command]
async fn save_project_state(project_dir: String, payload_json: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || save_project_state_blocking(project_dir, payload_json))
        .await
        .map_err(|e| coded_error("E_PROJECT_STATE_INTERNAL", format!("save project state task failed unexpectedly: {}", e)))?
}

#[tauri::command]
async fn load_project_state(project_dir: String) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || load_project_state_blocking(project_dir))
        .await
        .map_err(|e| coded_error("E_PROJECT_STATE_INTERNAL", format!("load project state task failed unexpectedly: {}", e)))?
}

#[tauri::command]
async fn export_diagnostic_bundle(output_path: String, payload_json: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let path = PathBuf::from(&output_path);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("无法创建诊断包目录 {}: {}", parent.display(), e))?;
        }
        std::fs::write(&path, payload_json)
            .map_err(|e| format!("无法写入诊断包 {}: {}", path.display(), e))?;
        Ok(path.display().to_string())
    })
    .await
    .map_err(|e| coded_error("E_DIAGNOSTIC_EXPORT_INTERNAL", format!("导出诊断包后台任务异常: {}", e)))?
}

#[tauri::command]
async fn load_project_documents_v5(project_dir: String) -> Result<ProjectDocumentsLoadResult, String> {
    tauri::async_runtime::spawn_blocking(move || load_project_documents_v5_blocking(project_dir))
        .await
        .map_err(|e| coded_error("E_PROJECT_LOAD_INTERNAL", format!("加载项目文档后台任务异常: {}", e)))?
}

#[tauri::command]
async fn load_build_report_summary(project_dir: String) -> Result<BuildReportSummary, String> {
    tauri::async_runtime::spawn_blocking(move || load_build_report_summary_blocking(project_dir))
        .await
        .map_err(|e| coded_error("E_BUILD_REPORT_INTERNAL", format!("鍔犺浇 build_report 鍚庡彴浠诲姟寮傚父: {}", e)))?
}

#[tauri::command]
async fn start_telemetry_session(app: AppHandle, telemetry_enabled: bool) -> Result<TelemetrySessionStartResponse, String> {
    tauri::async_runtime::spawn_blocking(move || start_telemetry_session_blocking(&app, telemetry_enabled))
        .await
        .map_err(|e| coded_error("E_TELEMETRY_INTERNAL", format!("鍚姩 telemetry session 鍚庡彴浠诲姟寮傚父: {}", e)))?
}

#[tauri::command]
async fn finish_telemetry_session(app: AppHandle, session_id: String, clean_exit: bool) -> Result<TelemetrySummary, String> {
    tauri::async_runtime::spawn_blocking(move || finish_telemetry_session_blocking(&app, session_id, clean_exit))
        .await
        .map_err(|e| coded_error("E_TELEMETRY_INTERNAL", format!("缁撴潫 telemetry session 鍚庡彴浠诲姟寮傚父: {}", e)))?
}

#[tauri::command]
async fn record_telemetry_event(app: AppHandle, payload_json: String) -> Result<TelemetrySummary, String> {
    tauri::async_runtime::spawn_blocking(move || record_telemetry_event_blocking(&app, payload_json))
        .await
        .map_err(|e| coded_error("E_TELEMETRY_INTERNAL", format!("璁板綍 telemetry event 鍚庡彴浠诲姟寮傚父: {}", e)))?
}

#[tauri::command]
async fn load_telemetry_summary(app: AppHandle) -> Result<TelemetrySummary, String> {
    tauri::async_runtime::spawn_blocking(move || load_telemetry_summary_blocking(&app))
        .await
        .map_err(|e| coded_error("E_TELEMETRY_INTERNAL", format!("鍔犺浇 telemetry summary 鍚庡彴浠诲姟寮傚父: {}", e)))?
}

#[tauri::command]
async fn clear_telemetry_history(app: AppHandle) -> Result<TelemetrySummary, String> {
    tauri::async_runtime::spawn_blocking(move || clear_telemetry_history_blocking(&app))
        .await
        .map_err(|e| coded_error("E_TELEMETRY_INTERNAL", format!("clear telemetry history failed unexpectedly: {}", e)))?
}

#[tauri::command]
async fn update_telemetry_settings(app: AppHandle, payload_json: String) -> Result<TelemetrySummary, String> {
    tauri::async_runtime::spawn_blocking(move || update_telemetry_settings_blocking(&app, payload_json))
        .await
        .map_err(|e| coded_error("E_TELEMETRY_INTERNAL", format!("update telemetry settings failed unexpectedly: {}", e)))?
}

#[tauri::command]
async fn flush_remote_telemetry_queue(app: AppHandle) -> Result<TelemetrySummary, String> {
    tauri::async_runtime::spawn_blocking(move || flush_remote_telemetry_queue_blocking(&app))
        .await
        .map_err(|e| coded_error("E_TELEMETRY_INTERNAL", format!("flush remote telemetry queue failed unexpectedly: {}", e)))?
}

#[tauri::command]
fn cancel_video(manager: State<'_, JobManager>, job_id: String) -> GenerateVideoResult {
    if let Ok(mut queued) = manager.queued.lock() {
        if let Some(index) = queued.iter().position(|job| job.id == job_id) {
            let job = queued.remove(index);
            job.cancelled.store(true, Ordering::SeqCst);
            return GenerateVideoResult {
                ok: true,
                code: Some("E_TASK_CANCELLED".to_string()),
                message: "Queued V5 render task cancelled.".to_string(),
                command_preview: String::new(),
                output_path: None,
                output_dir: None,
                cancelled: true,
                is_dry_run: false,
            };
        }
    }

    let job = manager
        .current
        .lock()
        .ok()
        .and_then(|current| current.clone());

    let Some(job) = job else {
        return GenerateVideoResult {
            ok: false,
            code: Some("E_NO_ACTIVE_TASK".to_string()),
            message: "当前没有正在生成的视频任务。".to_string(),
            command_preview: String::new(),
            output_path: None,
            output_dir: None,
            cancelled: false,
            is_dry_run: false,
        };
    };

    if job.id != job_id {
        return GenerateVideoResult {
            ok: false,
            code: Some("E_TASK_ID_MISMATCH".to_string()),
            message: "当前任务已经变化，请稍后再试。".to_string(),
            command_preview: String::new(),
            output_path: None,
            output_dir: None,
            cancelled: false,
            is_dry_run: false,
        };
    }

    job.cancelled.store(true, Ordering::SeqCst);
    kill_process_tree(job.pid);
    if let Ok(mut worker) = manager.worker.lock() {
        *worker = None;
    }

    GenerateVideoResult {
        ok: true,
        code: Some("E_TASK_CANCELLED".to_string()),
        message: "正在停止当前视频生成任务。".to_string(),
        command_preview: String::new(),
        output_path: None,
        output_dir: None,
        cancelled: true,
        is_dry_run: false,
    }
}

#[tauri::command]
fn open_in_explorer(path: String) {
    let target = PathBuf::from(path);
    let open_path = if target.is_file() {
        target
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| target.clone())
    } else if target.is_dir() {
        target
    } else if target.extension().is_some() {
        target
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| target.clone())
    } else {
        target
    };

    #[cfg(target_os = "windows")]
    {
        let mut cmd = Command::new("explorer");
        prepare_hidden_command(&mut cmd);
        let _ = cmd.arg(open_path).spawn();
    }

    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open").arg(open_path).spawn();
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let _ = Command::new("xdg-open").arg(open_path).spawn();
    }
}

// =========================
// V5 engine bridge
// =========================

#[tauri::command]
async fn scan_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    input_folder: String,
    project_dir: Option<String>,
    recursive: Option<bool>,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let workspace = project_workspace(&input_folder, project_dir)?;
        std::fs::create_dir_all(&workspace)
            .map_err(|e| coded_error("E_PROJECT_DIR_CREATE_FAILED", format!("无法创建 V5 项目目录 {}: {}", workspace.display(), e)))?;
        let output_path = workspace.join("media_library.json");
        run_v5_worker_json_task(
            &app,
            &manager,
            "v5-scan",
            json!({
                "type": "scan",
                "id": "v5-scan",
                "input_folder": input_folder.clone(),
                "output_path": output_path.display().to_string(),
                "recursive": recursive.unwrap_or(true),
            }),
            &output_path,
            "扫描失败",
        )
    })
    .await
    .map_err(|e| coded_error("E_SCAN_INTERNAL", format!("V5 scan 后台任务异常: {}", e)))?
}

#[tauri::command]
async fn plan_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    library_path: String,
    output_path: Option<String>,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let lib_path = PathBuf::from(&library_path);
        let output_path = output_path
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                lib_path
                    .parent()
                    .unwrap_or_else(|| Path::new("."))
                    .join("story_blueprint.json")
            });
        run_v5_worker_json_task(
            &app,
            &manager,
            "v5-plan",
            json!({
                "type": "plan",
                "id": "v5-plan",
                "library_path": library_path.clone(),
                "output_path": output_path.display().to_string(),
            }),
            &output_path,
            "生成蓝图失败",
        )
    })
    .await
    .map_err(|e| coded_error("E_PLAN_INTERNAL", format!("V5 plan 后台任务异常: {}", e)))?
}

#[tauri::command]
async fn save_blueprint_v5(path: String, content: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let target = PathBuf::from(path);
        if let Some(parent) = target.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| coded_error("E_BLUEPRINT_DIR_CREATE_FAILED", format!("无法创建蓝图目录: {}", e)))?;
        }
        std::fs::write(&target, content).map_err(|e| coded_error("E_BLUEPRINT_SAVE_FAILED", format!("无法保存蓝图: {}", e)))
    })
    .await
    .map_err(|e| coded_error("E_BLUEPRINT_SAVE_INTERNAL", format!("保存蓝图后台任务异常: {}", e)))?
}

#[tauri::command]
async fn save_timeline_v5(path: String, content: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let target = PathBuf::from(path);
        if let Some(parent) = target.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| coded_error("E_TIMELINE_DIR_CREATE_FAILED", format!("无法创建 timeline 目录: {}", e)))?;
        }
        std::fs::write(&target, content).map_err(|e| coded_error("E_TIMELINE_SAVE_FAILED", format!("无法保存 timeline: {}", e)))
    })
    .await
    .map_err(|e| coded_error("E_TIMELINE_SAVE_INTERNAL", format!("保存 timeline 后台任务异常: {}", e)))?
}

#[tauri::command]
async fn compile_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    blueprint_path: String,
    library_path: String,
    output_path: Option<String>,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let bp_path = PathBuf::from(&blueprint_path);
        let output_path = output_path
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                bp_path
                    .parent()
                    .unwrap_or_else(|| Path::new("."))
                    .join("render_plan.json")
            });
        run_v5_worker_json_task(
            &app,
            &manager,
            "v5-compile",
            json!({
                "type": "compile",
                "id": "v5-compile",
                "blueprint_path": blueprint_path.clone(),
                "library_path": library_path.clone(),
                "output_path": output_path.display().to_string(),
            }),
            &output_path,
            "编译渲染计划失败",
        )
    })
    .await
    .map_err(|e| coded_error("E_COMPILE_INTERNAL", format!("V5 compile 后台任务异常: {}", e)))?
}

#[tauri::command]
async fn timeline_generate_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    render_plan_path: String,
    output_path: String,
    blueprint_path: Option<String>,
    library_path: Option<String>,
    existing_timeline_path: Option<String>,
    project_dir: Option<String>,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let output_path_buf = PathBuf::from(&output_path);
        run_v5_worker_json_task(
            &app,
            &manager,
            "v5-timeline-generate",
            json!({
                "type": "timeline-generate",
                "id": "v5-timeline-generate",
                "render_plan_path": render_plan_path,
                "output_path": output_path,
                "blueprint_path": blueprint_path,
                "library_path": library_path,
                "existing_timeline_path": existing_timeline_path,
                "project_dir": project_dir,
            }),
            &output_path_buf,
            "生成 timeline 失败",
        )
    })
    .await
    .map_err(|e| coded_error("E_TIMELINE_GENERATE_INTERNAL", format!("V5 timeline generate 后台任务异常: {}", e)))?
}

#[tauri::command]
async fn timeline_compile_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    timeline_path: String,
    base_render_plan_path: String,
    output_path: String,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let output_path_buf = PathBuf::from(&output_path);
        run_v5_worker_json_task(
            &app,
            &manager,
            "v5-timeline-compile",
            json!({
                "type": "timeline-compile",
                "id": "v5-timeline-compile",
                "timeline_path": timeline_path,
                "base_render_plan_path": base_render_plan_path,
                "output_path": output_path,
            }),
            &output_path_buf,
            "Timeline 编译 render_plan 失败",
        )
    })
    .await
    .map_err(|e| coded_error("E_TIMELINE_COMPILE_INTERNAL", format!("V5 timeline compile 后台任务异常: {}", e)))?
}

#[tauri::command]
async fn timeline_preview_manifest_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    timeline_path: String,
    output_path: String,
    library_path: Option<String>,
    proxy_manifest_path: Option<String>,
    project_dir: Option<String>,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let output_path_buf = PathBuf::from(&output_path);
        run_v5_worker_json_task(
            &app,
            &manager,
            "v5-timeline-preview-manifest",
            json!({
                "type": "timeline-preview-manifest",
                "id": "v5-timeline-preview-manifest",
                "timeline_path": timeline_path,
                "output_path": output_path,
                "library_path": library_path,
                "proxy_manifest_path": proxy_manifest_path,
                "project_dir": project_dir,
            }),
            &output_path_buf,
            "Timeline preview manifest failed",
        )
    })
    .await
    .map_err(|e| coded_error("E_TIMELINE_PREVIEW_MANIFEST_INTERNAL", format!("V5 timeline preview manifest task failed: {}", e)))?
}

#[tauri::command]
async fn timeline_preview_assets_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    timeline_path: String,
    output_path: String,
    library_path: Option<String>,
    proxy_manifest_path: Option<String>,
    project_dir: Option<String>,
    batch_size: Option<i64>,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let output_path_buf = PathBuf::from(&output_path);
        run_v5_worker_json_task(
            &app,
            &manager,
            "v5-timeline-preview-assets",
            json!({
                "type": "timeline-preview-assets",
                "id": "v5-timeline-preview-assets",
                "timeline_path": timeline_path,
                "output_path": output_path,
                "library_path": library_path,
                "proxy_manifest_path": proxy_manifest_path,
                "project_dir": project_dir,
                "batch_size": batch_size.unwrap_or(8),
            }),
            &output_path_buf,
            "Timeline preview assets failed",
        )
    })
    .await
    .map_err(|e| coded_error("E_TIMELINE_PREVIEW_ASSETS_INTERNAL", format!("V5 timeline preview assets task failed: {}", e)))?
}

#[tauri::command]
async fn render_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    plan_path: String,
    output_path: String,
    params_json: String,
    job_id: Option<String>,
) -> Result<(), String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        render_v5_with_worker_blocking(app, manager, plan_path, output_path, params_json, job_id)
    })
    .await
    .map_err(|e| coded_error("E_RENDER_INTERNAL", format!("V5 render 后台任务异常: {}", e)))?
}

#[tauri::command]
async fn preview_title_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    title: String,
    subtitle: Option<String>,
    style_json: String,
    aspect_ratio: Option<String>,
    background: Option<String>,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut output_dir = app.path().app_cache_dir().unwrap_or_else(|_| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("scratch")
        });
        output_dir.push("title_previews");
        std::fs::create_dir_all(&output_dir)
            .map_err(|e| coded_error("E_TITLE_PREVIEW_CACHE_FAILED", format!("无法创建标题预览缓存目录 {}: {}", output_dir.display(), e)))?;

        let aspect_ratio = aspect_ratio.unwrap_or_else(|| "16:9".to_string());
        let background = background.unwrap_or_else(|| "travel".to_string());
        let subtitle = subtitle.unwrap_or_default();
        let cache_key = stable_hash(&format!(
            "{}|{}|{}|{}|{}",
            title, subtitle, style_json, aspect_ratio, background
        ));
        let output_path = output_dir.join(format!("title_preview_{}.mp4", cache_key));
        if output_path.is_file() {
            return Ok(output_path.display().to_string());
        }
        run_v5_worker_preview_task(
            &app,
            &manager,
            "v5-preview-title",
            json!({
                "type": "preview-title",
                "id": "v5-preview-title",
                "title": title.clone(),
                "subtitle": subtitle.clone(),
                "style": serde_json::from_str::<serde_json::Value>(&style_json).unwrap_or_else(|_| json!({})),
                "output_path": output_path.display().to_string(),
                "aspect_ratio": aspect_ratio.clone(),
                "background": background.clone(),
                "duration": 3.0,
            }),
            &output_path,
        )
    })
    .await
    .map_err(|e| coded_error("E_TITLE_PREVIEW_INTERNAL", format!("V5 title preview 后台任务异常: {}", e)))?
}

#[tauri::command]
async fn preview_render_v5(
    app: AppHandle,
    manager: State<'_, JobManager>,
    plan_path: String,
    params_json: String,
    max_duration: Option<f64>,
    max_segments: Option<u32>,
    height: Option<u32>,
    fps: Option<u32>,
) -> Result<String, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut output_dir = app.path().app_cache_dir().unwrap_or_else(|_| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("scratch")
        });
        output_dir.push("render_previews");
        std::fs::create_dir_all(&output_dir)
            .map_err(|e| coded_error("E_PREVIEW_CACHE_FAILED", format!("failed to create render preview cache {}: {}", output_dir.display(), e)))?;

        let plan_meta = std::fs::metadata(&plan_path)
            .map_err(|e| coded_error("E_RENDER_PLAN_METADATA_FAILED", format!("cannot read render plan metadata {}: {}", plan_path, e)))?;
        let modified_key = plan_meta
            .modified()
            .ok()
            .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|duration| duration.as_secs())
            .unwrap_or(0);
        let cache_key = stable_hash(&format!(
            "{}|{}|{}|{}|{}|{}|{}|{}",
            plan_path,
            plan_meta.len(),
            modified_key,
            params_json,
            max_duration.unwrap_or(20.0),
            max_segments.unwrap_or(8),
            height.unwrap_or(540),
            fps.unwrap_or(15)
        ));
        let output_path = output_dir.join(format!("render_preview_{}.mp4", cache_key));
        if output_path.is_file() {
            return Ok(output_path.display().to_string());
        }
        run_v5_worker_preview_task(
            &app,
            &manager,
            "v5-preview-render",
            json!({
                "type": "preview-render",
                "id": "v5-preview-render",
                "plan_path": plan_path.clone(),
                "output_path": output_path.display().to_string(),
                "params": serde_json::from_str::<serde_json::Value>(&params_json).unwrap_or_else(|_| json!({})),
                "height": height.unwrap_or(540),
                "fps": fps.unwrap_or(15),
                "max_duration": max_duration.unwrap_or(20.0),
                "max_segments": max_segments.unwrap_or(8),
            }),
            &output_path,
        )
    })
    .await
    .map_err(|e| coded_error("E_PREVIEW_RENDER_INTERNAL", format!("V5 render preview task failed: {}", e)))?
}

fn render_v5_with_worker_blocking(
    app: AppHandle,
    manager: JobManager,
    plan_path: String,
    output_path: String,
    params_json: String,
    job_id: Option<String>,
) -> Result<(), String> {
    let output_file = PathBuf::from(&output_path);
    if let Some(parent) = output_file.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("failed to create output directory {}: {}", parent.display(), e))?;
    }

    let job_id = job_id.unwrap_or_else(|| "v5-render-worker".to_string());
    let cancelled = Arc::new(AtomicBool::new(false));
    let task_params = serde_json::from_str::<serde_json::Value>(&params_json)
        .unwrap_or_else(|_| json!({}));

    let queue_position = enqueue_render_job(&app, &manager, &job_id, cancelled.clone())?;
    let _queue_guard = manager
        .queue_lock
        .lock()
        .map_err(|_| "render queue lock poisoned".to_string())?;
    remove_queued_job(&manager, &job_id);
    if cancelled.load(Ordering::SeqCst) {
        emit_render_queue_event(&app, &job_id, "cancelled", queue_position, Some("V5 render was cancelled before start"));
        return Err("V5 render was cancelled before start.".to_string());
    }
    emit_render_queue_event(&app, &job_id, "running", 0, Some("V5 render task started"));

    let result = run_v5_worker_task(
        &app,
        &manager,
        &job_id,
        cancelled.clone(),
        json!({
            "type": "render",
            "id": job_id,
            "plan_path": plan_path,
            "output_path": output_path,
            "params": task_params
        }),
    );
    clear_job(&manager, &job_id);

    if cancelled.load(Ordering::SeqCst) {
        emit_render_queue_event(&app, &job_id, "cancelled", 0, Some("V5 render was cancelled"));
        return Err("V5 render was cancelled.".to_string());
    }
    if let Err(err) = result {
        emit_render_queue_event(&app, &job_id, "failed", 0, Some(&err));
        return Err(err);
    }

    if !output_file.is_file() {
        let err = format!("V5 worker finished but output file was not created: {}", output_file.display());
        emit_render_queue_event(&app, &job_id, "failed", 0, Some(&err));
        return Err(err);
    }

    let payload = json!({
        "type": "result",
        "ok": true,
        "output_path": output_file.display().to_string(),
        "message": "V5 render completed by local worker"
    });
    let _ = app.emit("video-progress", payload.to_string());
    emit_render_queue_event(&app, &job_id, "done", 0, Some("V5 render task completed"));
    Ok(())
}

#[allow(dead_code)]
fn render_v5_blocking(
    app: AppHandle,
    manager: JobManager,
    plan_path: String,
    output_path: String,
    params_json: String,
    job_id: Option<String>,
) -> Result<(), String> {
    let script_path = find_v5_engine_script(&app)?;
    let output_file = PathBuf::from(&output_path);

    if let Some(parent) = output_file.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("无法创建输出目录 {}: {}", parent.display(), e))?;
    }

    let mut cmd = Command::new("python");
    prepare_python_command(&mut cmd);
    cmd.arg(&script_path)
        .arg("render")
        .arg("--plan")
        .arg(&plan_path)
        .arg("--output")
        .arg(&output_path)
        .arg("--params")
        .arg(&params_json)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(script_dir) = script_path.parent() {
        cmd.current_dir(script_dir);
    }

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("无法启动 V5 渲染进程: {}", e))?;

    let pid = child.id();
    let job_id = job_id.unwrap_or_else(|| format!("v5-render-{}", pid));
    let cancelled = Arc::new(AtomicBool::new(false));
    if let Ok(mut current) = manager.current.lock() {
        if current.is_some() {
            kill_process_tree(pid);
            return Err("已有视频正在生成，请先等待完成或停止当前任务。".to_string());
        }
        *current = Some(ActiveJob {
            id: job_id.clone(),
            pid,
            cancelled: cancelled.clone(),
        });
    }

    // stdout: Python V5 engine emits JSON progress events here.
    if let Some(stdout) = child.stdout.take() {
        let app_stdout = app.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                if let Ok(l) = line {
                    let _ = app_stdout.emit("video-progress", l);
                }
            }
        });
    }

    // stderr: wrap as {"type":"log"} instead of the old wrong {"event":"log"}.
    if let Some(stderr) = child.stderr.take() {
        let app_stderr = app.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(l) = line {
                    let payload = json!({
                        "type": "log",
                        "message": format!("ERROR: {}", l)
                    });
                    let _ = app_stderr.emit("video-progress", payload.to_string());
                }
            }
        });
    }

    let status = child
        .wait()
        .map_err(|e| format!("等待 V5 渲染进程失败: {}", e))?;

    let was_cancelled = cancelled.load(Ordering::SeqCst);
    clear_job(&manager, &job_id);

    if was_cancelled {
        return Err("已停止当前 V5 渲染任务。".to_string());
    }

    if !status.success() {
        return Err(format!("V5 渲染失败，退出状态: {}", status));
    }

    if !output_file.is_file() {
        return Err(format!(
            "V5 渲染进程已结束，但没有找到输出视频: {}",
            output_file.display()
        ));
    }

    let payload = json!({
        "type": "result",
        "ok": true,
        "output_path": output_file.display().to_string(),
        "message": "V5 视频渲染完成"
    });
    let _ = app.emit("video-progress", payload.to_string());

    Ok(())
}

// =========================
// Shared helpers
// =========================

fn run_v5_worker_task(
    app: &AppHandle,
    manager: &JobManager,
    job_id: &str,
    cancelled: Arc<AtomicBool>,
    task: serde_json::Value,
) -> Result<(), String> {
    let mut worker_guard = manager
        .worker
        .lock()
        .map_err(|_| "worker lock poisoned".to_string())?;

    if worker_guard.is_none() {
        *worker_guard = Some(start_v5_worker(app)?);
    }

    let worker = worker_guard.as_mut().ok_or_else(|| "worker not available".to_string())?;
    let pid = worker.child.id();
    if let Ok(mut current) = manager.current.lock() {
        if current.is_some() {
            return Err("another render task is already running".to_string());
        }
        *current = Some(ActiveJob {
            id: job_id.to_string(),
            pid,
            cancelled,
        });
    }

    let line = serde_json::to_string(&task).map_err(|e| format!("serialize worker task failed: {}", e))?;
    if let Err(err) = writeln!(worker.stdin, "{}", line).and_then(|_| worker.stdin.flush()) {
        *worker_guard = None;
        return Err(format!("write worker task failed: {}", err));
    }

    loop {
        let mut line = String::new();
        let bytes = match worker.stdout.read_line(&mut line) {
            Ok(bytes) => bytes,
            Err(err) => {
                *worker_guard = None;
                return Err(format!("read worker output failed: {}", err));
            }
        };
        if bytes == 0 {
            *worker_guard = None;
            return Err("worker exited before completing render task".to_string());
        }

        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let _ = app.emit("video-progress", trimmed.to_string());
        let Ok(value) = serde_json::from_str::<serde_json::Value>(trimmed) else {
            continue;
        };
        let event_type = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
        if event_type == "result" {
            if value.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) {
                return Ok(());
            }
            return Err(value.get("message").and_then(|v| v.as_str()).unwrap_or("worker task failed").to_string());
        }
        if event_type == "error" {
            *worker_guard = None;
            return Err(value.get("message").and_then(|v| v.as_str()).unwrap_or("worker task failed").to_string());
        }
    }
}

fn enqueue_render_job(
    app: &AppHandle,
    manager: &JobManager,
    job_id: &str,
    cancelled: Arc<AtomicBool>,
) -> Result<usize, String> {
    let position = {
        let mut queued = manager
            .queued
            .lock()
            .map_err(|_| "render queue lock poisoned".to_string())?;
        if queued.iter().any(|job| job.id == job_id) {
            return Err(format!("render job already queued: {}", job_id));
        }
        queued.push(QueuedJob {
            id: job_id.to_string(),
            cancelled,
        });
        queued.len()
    };
    emit_render_queue_event(app, job_id, "queued", position, Some("V5 render task queued"));
    Ok(position)
}

fn remove_queued_job(manager: &JobManager, job_id: &str) {
    if let Ok(mut queued) = manager.queued.lock() {
        if let Some(index) = queued.iter().position(|job| job.id == job_id) {
            queued.remove(index);
        }
    }
}

fn emit_render_queue_event(
    app: &AppHandle,
    job_id: &str,
    status: &str,
    position: usize,
    message: Option<&str>,
) {
    let payload = json!({
        "type": "render_queue",
        "job_id": job_id,
        "status": status,
        "position": position,
        "message": message.unwrap_or(status),
    });
    let _ = app.emit("video-progress", payload.to_string());
}

fn run_v5_worker_json_task(
    app: &AppHandle,
    manager: &JobManager,
    job_id: &str,
    task: serde_json::Value,
    output_path: &Path,
    error_prefix: &str,
) -> Result<String, String> {
    let cancelled = Arc::new(AtomicBool::new(false));
    let result = run_v5_worker_task(app, manager, job_id, cancelled, task);
    clear_job(manager, job_id);
    result.map_err(|e| format!("{}: {}", error_prefix, e))?;
    std::fs::read_to_string(output_path)
        .map_err(|e| format!("无法读取生成文件 {}: {}", output_path.display(), e))
}

fn run_v5_worker_preview_task(
    app: &AppHandle,
    manager: &JobManager,
    job_id: &str,
    task: serde_json::Value,
    output_path: &Path,
) -> Result<String, String> {
    let cancelled = Arc::new(AtomicBool::new(false));
    let result = run_v5_worker_task(app, manager, job_id, cancelled, task);
    clear_job(manager, job_id);
    result?;
    if !output_path.is_file() {
        return Err(format!(
            "worker finished but preview file was not created: {}",
            output_path.display()
        ));
    }
    Ok(output_path.display().to_string())
}

fn start_v5_worker(app: &AppHandle) -> Result<WorkerProcess, String> {
    let launch = find_v5_worker_entrypoint(app)?;
    let mut cmd = Command::new(&launch.program);
    match launch.kind {
        WorkerLaunchKind::BundledExecutable => prepare_hidden_command(&mut cmd),
        WorkerLaunchKind::PythonScript => prepare_python_command(&mut cmd),
    }
    cmd.args(&launch.args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(working_dir) = launch.working_dir.as_ref() {
        cmd.current_dir(working_dir);
    }

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("failed to start V5 worker: {}", e))?;
    let stdin = child.stdin.take().ok_or_else(|| "worker stdin unavailable".to_string())?;
    let stdout = child.stdout.take().ok_or_else(|| "worker stdout unavailable".to_string())?;

    if let Some(stderr) = child.stderr.take() {
        let app_stderr = app.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                let payload = json!({
                    "type": "log",
                    "message": format!("WORKER ERROR: {}", line)
                });
                let _ = app_stderr.emit("video-progress", payload.to_string());
            }
        });
    }

    let mut worker = WorkerProcess {
        child,
        stdin,
        stdout: BufReader::new(stdout),
    };

    let mut ready = String::new();
    worker
        .stdout
        .read_line(&mut ready)
        .map_err(|e| format!("failed to read worker ready event: {}", e))?;
    if !ready.trim().is_empty() {
        let _ = app.emit("video-progress", ready.trim().to_string());
    }
    Ok(worker)
}

fn project_workspace(input_folder: &str, project_dir: Option<String>) -> Result<PathBuf, String> {
    if let Some(dir) = project_dir {
        if !dir.trim().is_empty() {
            return Ok(PathBuf::from(dir));
        }
    }
    Ok(PathBuf::from(input_folder).join(".video_create_project"))
}

fn stable_hash(value: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    value.hash(&mut hasher);
    hasher.finish()
}


fn find_v5_engine_script(app: &AppHandle) -> Result<PathBuf, String> {
    find_script(
        app,
        "video_engine_v5.py",
        "无法找到 V5 引擎脚本 video_engine_v5.py。请确认它在项目根目录，或已作为 Tauri resource 打包。",
    )
}

fn find_v5_worker_script(app: &AppHandle) -> Result<PathBuf, String> {
    find_script(
        app,
        "video_engine_worker.py",
        "Cannot find V5 worker script video_engine_worker.py.",
    )
}

fn find_v5_worker_entrypoint(app: &AppHandle) -> Result<WorkerLaunchSpec, String> {
    resolve_worker_launch_spec(worker_executable_candidates(app), find_v5_worker_script(app).ok())
}

fn worker_executable_candidates(app: &AppHandle) -> Vec<PathBuf> {
    #[cfg(target_os = "windows")]
    let names = ["video-create-worker.exe"];
    #[cfg(not(target_os = "windows"))]
    let names = ["video-create-worker"];

    let mut candidates = Vec::new();

    if let Ok(resource_dir) = app.path().resource_dir() {
        for name in names {
            candidates.push(resource_dir.join(name));
            candidates.push(resource_dir.join("bin").join(name));
        }
    }

    if let Ok(current_dir) = std::env::current_dir() {
        for name in names {
            candidates.push(current_dir.join(name));
            candidates.push(current_dir.join("bin").join(name));
            candidates.push(current_dir.join("src-tauri").join("bin").join(name));
        }
        if let Some(parent) = current_dir.parent() {
            for name in names {
                candidates.push(parent.join(name));
                candidates.push(parent.join("bin").join(name));
                candidates.push(parent.join("src-tauri").join("bin").join(name));
            }
        }
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    for name in names {
        candidates.push(manifest_dir.join("bin").join(name));
        candidates.push(manifest_dir.join("..").join("src-tauri").join("bin").join(name));
    }

    candidates
}

fn resolve_worker_launch_spec(
    candidates: Vec<PathBuf>,
    script_path: Option<PathBuf>,
) -> Result<WorkerLaunchSpec, String> {
    for candidate in candidates {
        if candidate.is_file() {
            let working_dir = candidate.parent().map(Path::to_path_buf);
            return Ok(WorkerLaunchSpec {
                program: candidate,
                args: Vec::new(),
                working_dir,
                kind: WorkerLaunchKind::BundledExecutable,
            });
        }
    }

    let script_path = script_path.ok_or_else(|| {
        coded_error(
            "E_WORKER_ENTRYPOINT_MISSING",
            "Cannot find V5 worker executable or fallback script video_engine_worker.py.",
        )
    })?;
    let working_dir = script_path.parent().map(Path::to_path_buf);
    Ok(WorkerLaunchSpec {
        program: PathBuf::from("python"),
        args: vec![script_path.display().to_string()],
        working_dir,
        kind: WorkerLaunchKind::PythonScript,
    })
}

fn find_script(app: &AppHandle, file_name: &str, not_found_message: &str) -> Result<PathBuf, String> {
    let mut candidates = Vec::new();

    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join(file_name));
    }

    if let Ok(current_dir) = std::env::current_dir() {
        candidates.push(current_dir.join(file_name));
        if let Some(parent) = current_dir.parent() {
            candidates.push(parent.join(file_name));
        }
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    candidates.push(manifest_dir.join("..").join(file_name));
    candidates.push(manifest_dir.join(file_name));

    candidates
        .into_iter()
        .find(|path| path.is_file())
        .ok_or_else(|| not_found_message.to_string())
}

fn prepare_python_command(cmd: &mut Command) {
    prepare_hidden_command(cmd);
    cmd.env("PYTHONIOENCODING", "utf-8");
    cmd.env("PYTHONUTF8", "1");
}

fn prepare_hidden_command(cmd: &mut Command) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
}

fn startup_self_check_blocking(app: &AppHandle) -> Result<StartupDiagnostics, String> {
    let mut checks = Vec::new();

    checks.push(check_engine_resource(app));
    checks.push(check_worker_entrypoint(app));
    checks.push(check_worker_health(app));
    checks.push(check_named_writable_dir(app.path().app_data_dir(), "app_data", "Project data directory"));
    checks.push(check_named_writable_dir(app.path().app_cache_dir(), "app_cache", "Cache directory"));

    let ok = checks.iter().all(|check| check.ok);
    let failed = checks.iter().filter(|check| !check.ok).count();
    let summary = if ok {
        "Startup self-check passed.".to_string()
    } else {
        format!("Startup self-check found {} issue(s).", failed)
    };

    Ok(StartupDiagnostics {
        ok,
        code: if ok { None } else { Some("E_STARTUP_CHECK_FAILED".to_string()) },
        summary,
        checks,
    })
}

fn preflight_render_v5_blocking(
    input_folder: String,
    output_dir: String,
    plan_path: String,
    output_path: String,
) -> Result<StartupDiagnostics, String> {
    let input_folder = PathBuf::from(input_folder);
    let output_dir = PathBuf::from(output_dir);
    let plan_path = PathBuf::from(plan_path);
    let output_path = PathBuf::from(output_path);

    let mut checks = vec![
        check_existing_dir(&input_folder, "input_folder", "素材目录"),
        check_writable_dir(&output_dir, "output_dir", "输出目录"),
        check_existing_file(&plan_path, "render_plan", "渲染计划"),
        check_output_target(&output_path),
    ];

    if plan_path.is_file() {
        checks.push(check_render_plan_sources(&plan_path));
        checks.push(check_render_plan_scale(&plan_path));
    }

    let ok = checks.iter().all(|check| check.ok);
    let failed = checks.iter().filter(|check| !check.ok).count();
    let summary = if ok {
        "渲染前预检通过，可以开始最终渲染。".to_string()
    } else {
        format!("渲染前预检发现 {} 个问题，请处理后再渲染。", failed)
    };

    Ok(StartupDiagnostics {
        ok,
        code: if ok { None } else { Some("E_PREFLIGHT_CHECK_FAILED".to_string()) },
        summary,
        checks,
    })
}

fn check_engine_resource(app: &AppHandle) -> StartupCheckItem {
    match find_v5_engine_script(app) {
        Ok(path) => StartupCheckItem {
            id: "engine_resource".to_string(),
            label: "Render engine resource".to_string(),
            ok: true,
            code: None,
            message: "Engine script is available.".to_string(),
            detail: Some(path.display().to_string()),
        },
        Err(message) => StartupCheckItem {
            id: "engine_resource".to_string(),
            label: "Render engine resource".to_string(),
            ok: false,
            code: Some("E_ENGINE_RESOURCE_MISSING".to_string()),
            message,
            detail: None,
        },
    }
}

fn check_existing_dir(path: &Path, id: &str, label: &str) -> StartupCheckItem {
    if path.is_dir() {
        StartupCheckItem {
            id: id.to_string(),
            label: label.to_string(),
            ok: true,
            code: None,
            message: "目录存在且可访问。".to_string(),
            detail: Some(path.display().to_string()),
        }
    } else {
        StartupCheckItem {
            id: id.to_string(),
            label: label.to_string(),
            ok: false,
            code: Some("E_DIRECTORY_MISSING".to_string()),
            message: "目录不存在或不可访问。".to_string(),
            detail: Some(path.display().to_string()),
        }
    }
}

fn check_existing_file(path: &Path, id: &str, label: &str) -> StartupCheckItem {
    if path.is_file() {
        StartupCheckItem {
            id: id.to_string(),
            label: label.to_string(),
            ok: true,
            code: None,
            message: "文件存在且可读取。".to_string(),
            detail: Some(path.display().to_string()),
        }
    } else {
        StartupCheckItem {
            id: id.to_string(),
            label: label.to_string(),
            ok: false,
            code: Some("E_FILE_MISSING".to_string()),
            message: "文件不存在，请先完成故事蓝图确认并生成 render_plan.json。".to_string(),
            detail: Some(path.display().to_string()),
        }
    }
}

fn check_writable_dir(path: &Path, id: &str, label: &str) -> StartupCheckItem {
    match ensure_directory_writable(path) {
        Ok(()) => StartupCheckItem {
            id: id.to_string(),
            label: label.to_string(),
            ok: true,
            code: None,
            message: "目录可写。".to_string(),
            detail: Some(path.display().to_string()),
        },
        Err(err) => StartupCheckItem {
            id: id.to_string(),
            label: label.to_string(),
            ok: false,
            code: Some("E_DIRECTORY_NOT_WRITABLE".to_string()),
            message: err,
            detail: Some(path.display().to_string()),
        },
    }
}

fn check_output_target(output_path: &Path) -> StartupCheckItem {
    let parent = output_path.parent().unwrap_or_else(|| Path::new("."));
    match ensure_directory_writable(parent) {
        Ok(()) => {
            let exists_note = if output_path.exists() {
                "输出文件已存在，渲染时会覆盖同名文件。"
            } else {
                "输出文件路径可用。"
            };
            StartupCheckItem {
                id: "output_file".to_string(),
                label: "输出文件".to_string(),
                ok: true,
                code: None,
                message: exists_note.to_string(),
                detail: Some(output_path.display().to_string()),
            }
        }
        Err(err) => StartupCheckItem {
            id: "output_file".to_string(),
            label: "输出文件".to_string(),
            ok: false,
            code: Some("E_OUTPUT_NOT_WRITABLE".to_string()),
            message: format!("输出文件所在目录不可写: {}", err),
            detail: Some(output_path.display().to_string()),
        },
    }
}

fn check_render_plan_sources(plan_path: &Path) -> StartupCheckItem {
    let content = match std::fs::read_to_string(plan_path) {
        Ok(content) => content,
        Err(err) => {
            return StartupCheckItem {
                id: "media_sources".to_string(),
                label: "素材可读性".to_string(),
                ok: false,
                code: Some("E_RENDER_PLAN_READ_FAILED".to_string()),
                message: format!("无法读取渲染计划: {}", err),
                detail: Some(plan_path.display().to_string()),
            };
        }
    };
    let value: serde_json::Value = match serde_json::from_str(&content) {
        Ok(value) => value,
        Err(err) => {
            return StartupCheckItem {
                id: "media_sources".to_string(),
                label: "素材可读性".to_string(),
                ok: false,
                code: Some("E_RENDER_PLAN_INVALID_JSON".to_string()),
                message: format!("渲染计划 JSON 无法解析: {}", err),
                detail: Some(plan_path.display().to_string()),
            };
        }
    };

    let mut total_sources = 0usize;
    let mut missing = Vec::new();
    if let Some(segments) = value.get("segments").and_then(|v| v.as_array()) {
        for segment in segments {
            let Some(source) = segment.get("source_path").and_then(|v| v.as_str()) else {
                continue;
            };
            if source.trim().is_empty() {
                continue;
            }
            total_sources += 1;
            let source_path = PathBuf::from(source);
            if !source_path.is_file() {
                missing.push(source_path.display().to_string());
            }
        }
    }

    if missing.is_empty() {
        StartupCheckItem {
            id: "media_sources".to_string(),
            label: "素材可读性".to_string(),
            ok: true,
            code: None,
            message: format!("渲染计划中的 {} 个素材引用可访问。", total_sources),
            detail: None,
        }
    } else {
        StartupCheckItem {
            id: "media_sources".to_string(),
            label: "素材可读性".to_string(),
            ok: false,
            code: Some("E_MEDIA_SOURCE_MISSING".to_string()),
            message: format!("有 {} 个素材文件缺失或不可读取。", missing.len()),
            detail: Some(missing.into_iter().take(5).collect::<Vec<_>>().join("\n")),
        }
    }
}

fn check_render_plan_scale(plan_path: &Path) -> StartupCheckItem {
    let content = match std::fs::read_to_string(plan_path) {
        Ok(content) => content,
        Err(err) => {
            return StartupCheckItem {
                id: "render_scale".to_string(),
                label: "渲染规模".to_string(),
                ok: false,
                code: Some("E_RENDER_PLAN_READ_FAILED".to_string()),
                message: format!("无法读取渲染计划: {}", err),
                detail: Some(plan_path.display().to_string()),
            };
        }
    };
    let value: serde_json::Value = match serde_json::from_str(&content) {
        Ok(value) => value,
        Err(err) => {
            return StartupCheckItem {
                id: "render_scale".to_string(),
                label: "渲染规模".to_string(),
                ok: false,
                code: Some("E_RENDER_PLAN_INVALID_JSON".to_string()),
                message: format!("渲染计划 JSON 无法解析: {}", err),
                detail: Some(plan_path.display().to_string()),
            };
        }
    };
    let segment_count = value
        .get("segments")
        .and_then(|v| v.as_array())
        .map(|segments| segments.len())
        .unwrap_or(0);
    let total_duration = value
        .get("total_duration")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);
    let message = if total_duration >= 1800.0 || segment_count >= 300 {
        "检测到长视频或大量片段，建议使用稳定优先性能档位。"
    } else {
        "当前渲染规模正常。"
    };

    StartupCheckItem {
        id: "render_scale".to_string(),
        label: "渲染规模".to_string(),
        ok: true,
        code: if total_duration >= 1800.0 || segment_count >= 300 {
            Some("W_LARGE_RENDER_PLAN".to_string())
        } else {
            None
        },
        message: message.to_string(),
        detail: Some(format!("{} 个片段，预计 {:.1} 秒", segment_count, total_duration)),
    }
}

fn check_worker_entrypoint(app: &AppHandle) -> StartupCheckItem {
    match find_v5_worker_entrypoint(app) {
        Ok(launch) => {
            let mode = match launch.kind {
                WorkerLaunchKind::BundledExecutable => "Bundled executable",
                WorkerLaunchKind::PythonScript => "Python fallback",
            };
            StartupCheckItem {
                id: "worker_entrypoint".to_string(),
                label: "Worker entrypoint".to_string(),
                ok: true,
                code: None,
                message: format!("Resolved worker entrypoint via {}.", mode),
                detail: Some(launch.program.display().to_string()),
            }
        }
        Err(message) => StartupCheckItem {
            id: "worker_entrypoint".to_string(),
            label: "Worker entrypoint".to_string(),
            ok: false,
            code: Some("E_WORKER_ENTRYPOINT_MISSING".to_string()),
            message,
            detail: None,
        },
    }
}

fn check_worker_health(app: &AppHandle) -> StartupCheckItem {
    let launch = match find_v5_worker_entrypoint(app) {
        Ok(launch) => launch,
        Err(message) => {
            return StartupCheckItem {
                id: "worker_health".to_string(),
                label: "Worker health".to_string(),
                ok: false,
                code: Some("E_WORKER_ENTRYPOINT_MISSING".to_string()),
                message: format!("Health check skipped: {}", message),
                detail: None,
            };
        }
    };

    let mut cmd = Command::new(&launch.program);
    match launch.kind {
        WorkerLaunchKind::BundledExecutable => prepare_hidden_command(&mut cmd),
        WorkerLaunchKind::PythonScript => prepare_python_command(&mut cmd),
    }
    cmd.args(&launch.args)
        .arg("--health")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(working_dir) = launch.working_dir.as_ref() {
        cmd.current_dir(working_dir);
    }

    let output = match cmd.output() {
        Ok(output) => output,
        Err(err) => {
            return StartupCheckItem {
                id: "worker_health".to_string(),
                label: "Worker health".to_string(),
                ok: false,
                code: Some("E_WORKER_HEALTH_LAUNCH_FAILED".to_string()),
                message: format!("Failed to launch worker health probe: {}", err),
                detail: Some(launch.program.display().to_string()),
            };
        }
    };

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let detail = if !stderr.is_empty() {
            stderr
        } else {
            stdout
        };
        return StartupCheckItem {
            id: "worker_health".to_string(),
            label: "Worker health".to_string(),
            ok: false,
            code: Some("E_WORKER_HEALTH_FAILED".to_string()),
            message: format!("Worker health probe exited with {}.", output.status),
            detail: if detail.is_empty() { None } else { Some(detail) },
        };
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let parsed = serde_json::from_str::<serde_json::Value>(stdout.trim()).ok();
    let engine_version = parsed
        .as_ref()
        .and_then(|value| value.get("engine_version"))
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let encoders = parsed
        .as_ref()
        .and_then(|value| value.get("hardware_encoders"))
        .and_then(|value| value.as_array())
        .map(|values| {
            values
                .iter()
                .filter_map(|value| value.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        })
        .unwrap_or_else(String::new);
    let detail = if encoders.is_empty() {
        format!("engine_version={}", engine_version)
    } else {
        format!("engine_version={}, encoders={}", engine_version, encoders)
    };

    StartupCheckItem {
        id: "worker_health".to_string(),
        label: "Worker health".to_string(),
        ok: true,
        code: None,
        message: "Worker responded to health probe.".to_string(),
        detail: Some(detail),
    }
}

fn check_named_writable_dir<E: std::fmt::Display>(
    path_result: Result<PathBuf, E>,
    id: &str,
    label: &str,
) -> StartupCheckItem {
    let path = match path_result {
        Ok(path) => path,
        Err(err) => {
            return StartupCheckItem {
                id: id.to_string(),
                label: label.to_string(),
                ok: false,
                code: Some("E_DIRECTORY_RESOLVE_FAILED".to_string()),
                message: format!("Could not resolve directory: {}", err),
                detail: None,
            };
        }
    };

    match ensure_directory_writable(&path) {
        Ok(()) => StartupCheckItem {
            id: id.to_string(),
            label: label.to_string(),
            ok: true,
            code: None,
            message: "Directory is writable.".to_string(),
            detail: Some(path.display().to_string()),
        },
        Err(err) => StartupCheckItem {
            id: id.to_string(),
            label: label.to_string(),
            ok: false,
            code: Some("E_DIRECTORY_NOT_WRITABLE".to_string()),
            message: err,
            detail: Some(path.display().to_string()),
        },
    }
}

fn ensure_directory_writable(path: &Path) -> Result<(), String> {
    std::fs::create_dir_all(path)
        .map_err(|err| format!("Failed to create directory {}: {}", path.display(), err))?;
    let probe_path = path.join(".startup-self-check.tmp");
    std::fs::write(&probe_path, b"ok")
        .map_err(|err| format!("Failed to write probe file in {}: {}", path.display(), err))?;
    std::fs::remove_file(&probe_path)
        .map_err(|err| format!("Failed to remove probe file in {}: {}", path.display(), err))?;
    Ok(())
}

fn coded_error(code: impl AsRef<str>, message: impl Into<String>) -> String {
    format!("[{}] {}", code.as_ref(), message.into())
}

fn project_state_path(project_dir: &str) -> Result<PathBuf, String> {
    let trimmed = project_dir.trim();
    if trimmed.is_empty() {
        return Err(coded_error(
            "E_PROJECT_STATE_DIR_REQUIRED",
            "project_dir is required for project state autosave",
        ));
    }
    Ok(PathBuf::from(trimmed).join("project_state.json"))
}

fn session_snapshot_path(app: &AppHandle) -> Result<PathBuf, String> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("无法解析应用数据目录: {}", e))?;
    Ok(app_data_dir.join("session_snapshot.json"))
}

fn save_project_state_blocking(project_dir: String, payload_json: String) -> Result<(), String> {
    let path = project_state_path(&project_dir)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| {
            coded_error(
                "E_PROJECT_STATE_DIR_CREATE_FAILED",
                format!("failed to create project state directory {}: {}", parent.display(), e),
            )
        })?;
    }
    std::fs::write(&path, payload_json).map_err(|e| {
        coded_error(
            "E_PROJECT_STATE_WRITE_FAILED",
            format!("failed to write project state {}: {}", path.display(), e),
        )
    })
}

fn load_project_state_blocking(project_dir: String) -> Result<Option<String>, String> {
    let path = project_state_path(&project_dir)?;
    if !path.is_file() {
        return Ok(None);
    }
    let content = std::fs::read_to_string(&path).map_err(|e| {
        coded_error(
            "E_PROJECT_STATE_READ_FAILED",
            format!("failed to read project state {}: {}", path.display(), e),
        )
    })?;
    Ok(Some(content))
}

fn telemetry_store_path(app: &AppHandle) -> Result<PathBuf, String> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("鏃犳硶瑙ｆ瀽 telemetry 鏁版嵁鐩綍: {}", e))?;
    Ok(app_data_dir.join("telemetry_store.json"))
}

fn load_telemetry_store(path: &Path) -> Result<TelemetryStore, String> {
    if !path.is_file() {
        return Ok(TelemetryStore::default());
    }
    let raw = std::fs::read_to_string(path)
        .map_err(|e| coded_error("E_TELEMETRY_READ_FAILED", format!("鏃犳硶璇诲彇 telemetry store {}: {}", path.display(), e)))?;
    let mut store: TelemetryStore = serde_json::from_str(&raw)
        .map_err(|e| coded_error("E_TELEMETRY_INVALID_JSON", format!("telemetry store JSON 鏃犳硶瑙ｆ瀽 {}: {}", path.display(), e)))?;
    if store.schema_version.is_empty() {
        store.schema_version = TELEMETRY_SCHEMA_VERSION.to_string();
    }
    Ok(store)
}

fn save_telemetry_store(path: &Path, store: &TelemetryStore) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| coded_error("E_TELEMETRY_WRITE_FAILED", format!("鏃犳硶鍒涘缓 telemetry 鐩綍 {}: {}", parent.display(), e)))?;
    }
    let serialized = serde_json::to_string_pretty(store)
        .map_err(|e| coded_error("E_TELEMETRY_WRITE_FAILED", format!("鏃犳硶搴忓垪鍖? telemetry store: {}", e)))?;
    std::fs::write(path, serialized)
        .map_err(|e| coded_error("E_TELEMETRY_WRITE_FAILED", format!("鏃犳硶鍐欏叆 telemetry store {}: {}", path.display(), e)))
}

fn current_timestamp_iso() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    format!("{}", seconds)
}

fn next_telemetry_session_id() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    format!("session-{}", nanos)
}

fn next_telemetry_remote_event_id() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    format!("remote-{}", nanos)
}

fn normalize_remote_endpoint(endpoint: Option<String>) -> Option<String> {
    endpoint.and_then(|value| {
        let trimmed = value.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    })
}

fn is_valid_remote_endpoint(endpoint: &str) -> bool {
    endpoint.starts_with("https://") || endpoint.starts_with("http://127.0.0.1") || endpoint.starts_with("http://localhost")
}

fn remote_endpoint_host(endpoint: &str) -> Option<String> {
    let without_scheme = endpoint
        .strip_prefix("https://")
        .or_else(|| endpoint.strip_prefix("http://"))
        .unwrap_or(endpoint);
    let host = without_scheme.split('/').next().unwrap_or("").trim();
    if host.is_empty() {
        None
    } else {
        Some(host.to_string())
    }
}

fn summarize_count_map(map: &HashMap<String, u64>, limit: usize) -> Vec<TelemetryCountEntry> {
    let mut entries = map
        .iter()
        .map(|(key, count)| TelemetryCountEntry {
            key: key.clone(),
            count: *count,
        })
        .collect::<Vec<_>>();
    entries.sort_by(|left, right| {
        right
            .count
            .cmp(&left.count)
            .then_with(|| left.key.cmp(&right.key))
    });
    entries.truncate(limit);
    entries
}

fn telemetry_summary_from_store(store: &TelemetryStore) -> TelemetrySummary {
    let crash_free_session_rate = if store.summary.sessions_started > 0 {
        store.summary.sessions_completed_cleanly as f64 / store.summary.sessions_started as f64
    } else {
        0.0
    };
    let first_export_success_rate = if store.summary.first_export_sessions > 0 {
        store.summary.first_export_successes as f64 / store.summary.first_export_sessions as f64
    } else {
        0.0
    };

    TelemetrySummary {
        telemetry_enabled: store.preference_enabled,
        current_consent_version: TELEMETRY_CONSENT_VERSION.to_string(),
        consent_accepted_version: store.remote.consent_accepted_version.clone(),
        remote_upload_enabled: store.remote.remote_upload_enabled,
        remote_endpoint_configured: store.remote.remote_endpoint.is_some(),
        remote_endpoint: store.remote.remote_endpoint.clone(),
        remote_endpoint_host: store
            .remote
            .remote_endpoint
            .as_deref()
            .and_then(remote_endpoint_host),
        pending_remote_events: store.remote.pending_events.len() as u64,
        last_remote_upload_at: store.remote.last_upload_at.clone(),
        last_remote_upload_error: store.remote.last_upload_error.clone(),
        sessions_started: store.summary.sessions_started,
        sessions_completed_cleanly: store.summary.sessions_completed_cleanly,
        sessions_crashed: store.summary.sessions_crashed,
        crash_free_session_rate,
        first_export_sessions: store.summary.first_export_sessions,
        first_export_successes: store.summary.first_export_successes,
        first_export_success_rate,
        render_attempts: store.summary.render_attempts,
        render_successes: store.summary.render_successes,
        render_failures: store.summary.render_failures,
        recovery_resumable_events: store.summary.recovery_resumable_events,
        recovery_retryable_events: store.summary.recovery_retryable_events,
        top_error_codes: summarize_count_map(&store.summary.error_codes, 5),
        top_support_queues: summarize_count_map(&store.summary.support_queues, 5),
        top_tags: summarize_count_map(&store.summary.tags, 8),
        top_severities: summarize_count_map(&store.summary.severities, 5),
        recent_events: store.recent_events.clone(),
        last_updated_at: store.summary.last_updated_at.clone(),
    }
}

fn telemetry_start_session(store: &mut TelemetryStore, telemetry_enabled: bool) -> (Option<String>, bool) {
    let mut previous_session_recovered_as_crash = false;
    if let Some(active) = store.active_session.take() {
        if active.telemetry_enabled {
            store.summary.sessions_crashed += 1;
            store.summary.last_updated_at = Some(current_timestamp_iso());
            previous_session_recovered_as_crash = true;
        }
    }

    store.preference_enabled = telemetry_enabled;
    if !telemetry_enabled {
        return (None, previous_session_recovered_as_crash);
    }

    store.summary.sessions_started += 1;
    store.summary.last_updated_at = Some(current_timestamp_iso());
    let session_id = next_telemetry_session_id();
    store.active_session = Some(ActiveTelemetrySession {
        session_id: session_id.clone(),
        started_at: current_timestamp_iso(),
        telemetry_enabled: true,
        first_export_recorded: false,
    });
    (Some(session_id), previous_session_recovered_as_crash)
}

fn telemetry_finish_session(store: &mut TelemetryStore, session_id: &str, clean_exit: bool) {
    let matches_active = store
        .active_session
        .as_ref()
        .map(|active| active.session_id == session_id)
        .unwrap_or(false);
    if !matches_active {
        return;
    }
    let active = store.active_session.take();
    if active.as_ref().map(|item| item.telemetry_enabled).unwrap_or(false) {
        if clean_exit {
            store.summary.sessions_completed_cleanly += 1;
        } else {
            store.summary.sessions_crashed += 1;
        }
        store.summary.last_updated_at = Some(current_timestamp_iso());
    }
}

fn increment_counter(map: &mut HashMap<String, u64>, key: Option<String>) {
    let Some(key) = key else { return };
    if key.trim().is_empty() {
        return;
    }
    *map.entry(key).or_insert(0) += 1;
}

fn telemetry_record_event(store: &mut TelemetryStore, payload: TelemetryEventPayload) {
    if !store.preference_enabled {
        return;
    }

    let event = TelemetryEventRecord {
        session_id: payload.session_id.clone(),
        event_type: payload.event_type.clone(),
        timestamp: payload.timestamp.clone().unwrap_or_else(current_timestamp_iso),
        success: payload.success,
        error_code: payload.error_code.clone(),
        support_queue: payload.support_queue.clone(),
        severity: payload.severity.clone(),
        tags: payload.tags.clone().unwrap_or_default(),
        recovery_resumable: payload.recovery_resumable.unwrap_or(false),
        recovery_retryable: payload.recovery_retryable.unwrap_or(false),
        recovery_completed_chunks: payload.recovery_completed_chunks.unwrap_or(0),
        recovery_reused_chunks: payload.recovery_reused_chunks.unwrap_or(0),
    };

    if payload.event_type == "render_result" {
        store.summary.render_attempts += 1;
        if payload.success.unwrap_or(false) {
            store.summary.render_successes += 1;
        } else {
            store.summary.render_failures += 1;
        }

        if payload.first_export.unwrap_or(false) {
            if let Some(active) = store.active_session.as_mut() {
                if !active.first_export_recorded {
                    active.first_export_recorded = true;
                    store.summary.first_export_sessions += 1;
                    if payload.success.unwrap_or(false) {
                        store.summary.first_export_successes += 1;
                    }
                }
            }
        }
    }

    if event.recovery_resumable {
        store.summary.recovery_resumable_events += 1;
    }
    if event.recovery_retryable {
        store.summary.recovery_retryable_events += 1;
    }

    increment_counter(&mut store.summary.error_codes, event.error_code.clone());
    increment_counter(&mut store.summary.support_queues, event.support_queue.clone());
    increment_counter(&mut store.summary.severities, event.severity.clone());
    for tag in &event.tags {
        increment_counter(&mut store.summary.tags, Some(tag.clone()));
    }

    store.recent_events.push(event.clone());
    if store.recent_events.len() > 40 {
        let drain_count = store.recent_events.len() - 40;
        store.recent_events.drain(0..drain_count);
    }
    store.summary.last_updated_at = Some(current_timestamp_iso());

    if store.remote.remote_upload_enabled
        && store.remote.consent_accepted_version.as_deref() == Some(TELEMETRY_CONSENT_VERSION)
        && store.remote.remote_endpoint.is_some()
    {
        store.remote.pending_events.push(TelemetryRemoteEnvelope {
            id: next_telemetry_remote_event_id(),
            queued_at: current_timestamp_iso(),
            app_version: env!("CARGO_PKG_VERSION").to_string(),
            consent_version: TELEMETRY_CONSENT_VERSION.to_string(),
            event,
        });
        if store.remote.pending_events.len() > MAX_PENDING_REMOTE_EVENTS {
            let drain_count = store.remote.pending_events.len() - MAX_PENDING_REMOTE_EVENTS;
            store.remote.pending_events.drain(0..drain_count);
        }
    }
}

fn telemetry_clear_history(store: &mut TelemetryStore) {
    let preference_enabled = store.preference_enabled;
    let active_session = store.active_session.clone().map(|mut session| {
        session.first_export_recorded = false;
        session
    });

    store.summary = TelemetryAggregate::default();
    store.recent_events.clear();
    store.remote.pending_events.clear();
    store.remote.last_upload_at = None;
    store.remote.last_upload_error = None;
    store.preference_enabled = preference_enabled;
    store.active_session = active_session;

    if store
        .active_session
        .as_ref()
        .map(|session| session.telemetry_enabled)
        .unwrap_or(false)
    {
        store.summary.sessions_started = 1;
        store.summary.last_updated_at = Some(current_timestamp_iso());
    }
}

fn flush_remote_queue_if_possible(store: &mut TelemetryStore) {
    if !store.remote.remote_upload_enabled {
        return;
    }
    if store.remote.consent_accepted_version.as_deref() != Some(TELEMETRY_CONSENT_VERSION) {
        return;
    }
    let Some(endpoint) = store.remote.remote_endpoint.clone() else {
        return;
    };
    if store.remote.pending_events.is_empty() {
        store.remote.last_upload_error = None;
        return;
    }

    let payload = json!({
        "schemaVersion": TELEMETRY_SCHEMA_VERSION,
        "consentVersion": TELEMETRY_CONSENT_VERSION,
        "generatedAt": current_timestamp_iso(),
        "appVersion": env!("CARGO_PKG_VERSION"),
        "events": store.remote.pending_events.clone(),
    });

    let payload_string = payload.to_string();
    let mut child = match Command::new("curl")
        .args([
            "--silent",
            "--show-error",
            "--fail",
            "--max-time",
            "5",
            "-X",
            "POST",
            "-H",
            "content-type: application/json",
            "--data-binary",
            "@-",
            endpoint.as_str(),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(child) => child,
        Err(error) => {
            store.remote.last_upload_error = Some(format!("failed to launch curl uploader: {}", error));
            return;
        }
    };

    if let Some(stdin) = child.stdin.as_mut() {
        if let Err(error) = stdin.write_all(payload_string.as_bytes()) {
            store.remote.last_upload_error = Some(format!("failed to stream telemetry payload: {}", error));
            return;
        }
    }

    match child.wait_with_output() {
        Ok(output) if output.status.success() => {
            store.remote.pending_events.clear();
            store.remote.last_upload_at = Some(current_timestamp_iso());
            store.remote.last_upload_error = None;
        }
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            store.remote.last_upload_error = Some(if stderr.is_empty() {
                format!("remote upload returned status {}", output.status)
            } else {
                format!("remote upload failed: {}", stderr)
            });
        }
        Err(error) => {
            store.remote.last_upload_error = Some(format!("failed to wait for curl uploader: {}", error));
        }
    }
}

fn apply_telemetry_settings(store: &mut TelemetryStore, payload: TelemetrySettingsPayload) -> Result<(), String> {
    if let Some(version) = payload.consent_accepted_version {
        if version == TELEMETRY_CONSENT_VERSION {
            store.remote.consent_accepted_version = Some(version);
        } else {
            return Err(coded_error(
                "E_TELEMETRY_CONSENT_VERSION_MISMATCH",
                format!("telemetry consent version mismatch: expected {}", TELEMETRY_CONSENT_VERSION),
            ));
        }
    }

    if let Some(remote_upload_enabled) = payload.remote_upload_enabled {
        store.remote.remote_upload_enabled = remote_upload_enabled;
    }

    let remote_endpoint_present = payload.remote_endpoint.is_some();
    if let Some(endpoint) = normalize_remote_endpoint(payload.remote_endpoint) {
        if !is_valid_remote_endpoint(&endpoint) {
            return Err(coded_error(
                "E_TELEMETRY_REMOTE_ENDPOINT_INVALID",
                "remote telemetry endpoint must use https, or http only for localhost".to_string(),
            ));
        }
        store.remote.remote_endpoint = Some(endpoint);
    } else if remote_endpoint_present {
        store.remote.remote_endpoint = None;
    }

    if store.remote.remote_upload_enabled && store.remote.remote_endpoint.is_none() {
        store.remote.remote_upload_enabled = false;
        store.remote.last_upload_error = Some("remote upload disabled because no endpoint is configured".to_string());
    }

    Ok(())
}

fn start_telemetry_session_blocking(app: &AppHandle, telemetry_enabled: bool) -> Result<TelemetrySessionStartResponse, String> {
    let path = telemetry_store_path(app)?;
    let mut store = load_telemetry_store(&path)?;
    let (session_id, previous_session_recovered_as_crash) = telemetry_start_session(&mut store, telemetry_enabled);
    save_telemetry_store(&path, &store)?;
    let summary = telemetry_summary_from_store(&store);
    Ok(TelemetrySessionStartResponse {
        session_id,
        telemetry_enabled,
        previous_session_recovered_as_crash,
        summary,
    })
}

fn finish_telemetry_session_blocking(app: &AppHandle, session_id: String, clean_exit: bool) -> Result<TelemetrySummary, String> {
    let path = telemetry_store_path(app)?;
    let mut store = load_telemetry_store(&path)?;
    telemetry_finish_session(&mut store, &session_id, clean_exit);
    save_telemetry_store(&path, &store)?;
    Ok(telemetry_summary_from_store(&store))
}

fn record_telemetry_event_blocking(app: &AppHandle, payload_json: String) -> Result<TelemetrySummary, String> {
    let payload: TelemetryEventPayload = serde_json::from_str(&payload_json)
        .map_err(|e| coded_error("E_TELEMETRY_INVALID_JSON", format!("telemetry event JSON 鏃犳硶瑙ｆ瀽: {}", e)))?;
    let path = telemetry_store_path(app)?;
    let mut store = load_telemetry_store(&path)?;
    telemetry_record_event(&mut store, payload);
    flush_remote_queue_if_possible(&mut store);
    save_telemetry_store(&path, &store)?;
    Ok(telemetry_summary_from_store(&store))
}

fn load_telemetry_summary_blocking(app: &AppHandle) -> Result<TelemetrySummary, String> {
    let path = telemetry_store_path(app)?;
    let store = load_telemetry_store(&path)?;
    Ok(telemetry_summary_from_store(&store))
}

fn clear_telemetry_history_blocking(app: &AppHandle) -> Result<TelemetrySummary, String> {
    let path = telemetry_store_path(app)?;
    let mut store = load_telemetry_store(&path)?;
    telemetry_clear_history(&mut store);
    save_telemetry_store(&path, &store)?;
    Ok(telemetry_summary_from_store(&store))
}

fn update_telemetry_settings_blocking(app: &AppHandle, payload_json: String) -> Result<TelemetrySummary, String> {
    let payload: TelemetrySettingsPayload = serde_json::from_str(&payload_json)
        .map_err(|e| coded_error("E_TELEMETRY_INVALID_JSON", format!("telemetry settings JSON invalid: {}", e)))?;
    let path = telemetry_store_path(app)?;
    let mut store = load_telemetry_store(&path)?;
    apply_telemetry_settings(&mut store, payload)?;
    flush_remote_queue_if_possible(&mut store);
    save_telemetry_store(&path, &store)?;
    Ok(telemetry_summary_from_store(&store))
}

fn flush_remote_telemetry_queue_blocking(app: &AppHandle) -> Result<TelemetrySummary, String> {
    let path = telemetry_store_path(app)?;
    let mut store = load_telemetry_store(&path)?;
    flush_remote_queue_if_possible(&mut store);
    save_telemetry_store(&path, &store)?;
    Ok(telemetry_summary_from_store(&store))
}

fn load_project_documents_v5_blocking(project_dir: String) -> Result<ProjectDocumentsLoadResult, String> {
    let root = PathBuf::from(&project_dir);
    if !root.is_dir() {
        return Err(coded_error(
            "E_PROJECT_DIR_MISSING",
            format!("项目目录不存在或不可访问: {}", root.display()),
        ));
    }

    let mut migration_notes = Vec::new();
    let mut migrated = false;

    let library = load_and_migrate_project_doc(&root.join("media_library.json"), "media_library", &mut migrated, &mut migration_notes)?;
    let blueprint = load_and_migrate_project_doc(&root.join("story_blueprint.json"), "story_blueprint", &mut migrated, &mut migration_notes)?;
    let render_plan = load_and_migrate_project_doc(&root.join("render_plan.json"), "render_plan", &mut migrated, &mut migration_notes)?;
    let timeline = load_timeline_doc_resilient(&root, &library, &blueprint, &render_plan, &mut migrated, &mut migration_notes)?;
    let timeline_preview_manifest = load_and_migrate_project_doc(
        &root.join("timeline_preview_manifest.json"),
        "timeline_preview_manifest",
        &mut migrated,
        &mut migration_notes,
    )?;

    Ok(ProjectDocumentsLoadResult {
        project_dir,
        migrated,
        migration_notes,
        library,
        blueprint,
        render_plan,
        timeline,
        timeline_preview_manifest,
    })
}

fn load_build_report_summary_blocking(project_dir: String) -> Result<BuildReportSummary, String> {
    let root = PathBuf::from(&project_dir);
    if !root.is_dir() {
        return Err(coded_error(
            "E_PROJECT_DIR_MISSING",
            format!("椤圭洰鐩綍涓嶅瓨鍦ㄦ垨涓嶅彲璁块棶: {}", root.display()),
        ));
    }

    let report_path = root.join("build_report.json");
    if !report_path.is_file() {
        return Err(coded_error(
            "E_BUILD_REPORT_MISSING",
            format!("鏈壘鍒?build_report.json: {}", report_path.display()),
        ));
    }

    let raw = std::fs::read_to_string(&report_path).map_err(|e| {
        coded_error(
            "E_BUILD_REPORT_READ_FAILED",
            format!("鏃犳硶璇诲彇 build_report.json {}: {}", report_path.display(), e),
        )
    })?;
    let value: Value = serde_json::from_str(&raw).map_err(|e| {
        coded_error(
            "E_BUILD_REPORT_INVALID_JSON",
            format!("build_report.json JSON 鏃犳硶瑙ｆ瀽 {}: {}", report_path.display(), e),
        )
    })?;

    Ok(extract_build_report_summary(value, &report_path))
}

fn extract_build_report_summary(value: Value, report_path: &Path) -> BuildReportSummary {
    let recovery = value.get("recovery").and_then(|item| item.as_object());
    let failure = value.get("failure").and_then(|item| item.as_object());
    let backend = value.get("backend").and_then(|item| item.as_object());
    let observability = value
        .get("diagnostics")
        .and_then(|item| item.get("observability"))
        .and_then(|item| item.as_object());
    let fast_path = observability
        .and_then(|item| item.get("fast_path_coverage"))
        .and_then(|item| item.as_object());
    let route_differences = observability
        .and_then(|item| item.get("route_differences"))
        .and_then(|item| item.get("segments"))
        .and_then(|item| item.as_object());

    BuildReportSummary {
        report_path: report_path.display().to_string(),
        manifest_path: recovery
            .and_then(|item| item.get("manifest_path"))
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        build_report_version: value
            .get("build_report_version")
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        timeline_summary: value.get("timeline_summary").cloned(),
        route_summary: value.get("route_summary").cloned(),
        fallback_summary: value.get("fallback_summary").cloned(),
        cache_summary: value.get("cache_summary").cloned(),
        recompute_summary: value.get("recompute_summary").cloned(),
        performance_summary: value.get("performance_summary").cloned(),
        quality_summary: value.get("quality_summary").cloned(),
        recovery_summary: value.get("recovery_summary").cloned(),
        migration_notes: value
            .get("migration_notes")
            .and_then(|item| item.as_array())
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| item.as_str().map(|value| value.to_string()))
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default(),
        report_suggestions: value.get("report_suggestions").cloned(),
        status: value.get("status").and_then(|item| item.as_str()).map(|item| item.to_string()),
        render_intent: value
            .get("render_intent")
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        render_mode: value
            .get("render_mode")
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        failed_stage: value
            .get("failed_stage")
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        output_path: value
            .get("output_path")
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        selected_backend: value
            .get("selected_backend")
            .and_then(|item| item.as_str())
            .or_else(|| backend.and_then(|item| item.get("selected_backend")).and_then(|item| item.as_str()))
            .map(|item| item.to_string()),
        actual_backend: value
            .get("actual_backend")
            .and_then(|item| item.as_str())
            .or_else(|| backend.and_then(|item| item.get("actual_backend_name")).and_then(|item| item.as_str()))
            .map(|item| item.to_string()),
        backend_reason: value
            .get("backend_reason")
            .and_then(|item| item.as_str())
            .or_else(|| backend.and_then(|item| item.get("reason")).and_then(|item| item.as_str()))
            .map(|item| item.to_string()),
        fallback_chain: value
            .get("fallback_chain")
            .and_then(|item| item.as_array())
            .or_else(|| backend.and_then(|item| item.get("fallback_chain")).and_then(|item| item.as_array()))
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| item.as_str().map(|value| value.to_string()))
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default(),
        fallback_used: value
            .get("fallback_used")
            .and_then(|item| item.as_str())
            .or_else(|| backend.and_then(|item| item.get("fallback_used")).and_then(|item| item.as_str()))
            .map(|item| item.to_string()),
        fallback_reason: value
            .get("fallback_reason")
            .and_then(|item| item.as_str())
            .or_else(|| backend.and_then(|item| item.get("fallback_reason")).and_then(|item| item.as_str()))
            .map(|item| item.to_string()),
        fallback_applied: value
            .get("fallback_applied")
            .and_then(|item| item.as_bool())
            .or_else(|| backend.and_then(|item| item.get("fallback_applied")).and_then(|item| item.as_bool()))
            .unwrap_or(false),
        chunk_count: value.get("chunk_count").and_then(|item| item.as_u64()).map(|item| item as usize),
        segment_fast_path_rate: value
            .get("segment_fast_path_rate")
            .and_then(|item| item.as_f64())
            .or_else(|| {
                fast_path
                    .and_then(|item| item.get("segments"))
                    .and_then(|item| item.get("fast_path_rate"))
                    .and_then(|item| item.as_f64())
            }),
        chunk_fast_path_rate: value
            .get("chunk_fast_path_rate")
            .and_then(|item| item.as_f64())
            .or_else(|| {
                fast_path
                    .and_then(|item| item.get("chunks"))
                    .and_then(|item| item.get("fast_path_rate"))
                    .and_then(|item| item.as_f64())
            }),
        segment_route_difference_count: value
            .get("segment_route_difference_count")
            .and_then(|item| item.as_u64())
            .or_else(|| route_differences.and_then(|item| item.get("changed_count")).and_then(|item| item.as_u64()))
            .unwrap_or(0) as usize,
        segment_route_difference_rate: value
            .get("segment_route_difference_rate")
            .and_then(|item| item.as_f64())
            .or_else(|| route_differences.and_then(|item| item.get("changed_rate")).and_then(|item| item.as_f64())),
        created_at: value
            .get("created_at")
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        resumable: recovery
            .and_then(|item| item.get("resumable"))
            .and_then(|item| item.as_bool())
            .unwrap_or(false),
        resumed_from_manifest: recovery
            .and_then(|item| item.get("resumed_from_manifest"))
            .and_then(|item| item.as_bool())
            .unwrap_or(false),
        reused_chunk_count: recovery
            .and_then(|item| item.get("reused_chunk_count"))
            .and_then(|item| item.as_u64())
            .unwrap_or(0) as usize,
        completed_chunk_count: recovery
            .and_then(|item| item.get("completed_chunk_count"))
            .and_then(|item| item.as_u64())
            .unwrap_or(0) as usize,
        failed_chunk_count: recovery
            .and_then(|item| item.get("failed_chunk_count"))
            .and_then(|item| item.as_u64())
            .unwrap_or(0) as usize,
        reported_chunk_count: recovery
            .and_then(|item| item.get("reported_chunk_count"))
            .and_then(|item| item.as_u64())
            .unwrap_or(0) as usize,
        failed_chunk: recovery
            .and_then(|item| item.get("failed_chunk"))
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        failure_code: failure
            .and_then(|item| item.get("code"))
            .and_then(|item| item.as_str())
            .map(|item| item.to_string()),
        failure_message: failure
            .and_then(|item| item.get("message"))
            .and_then(|item| item.as_str())
            .map(|item| item.to_string())
            .or_else(|| value.get("error").and_then(|item| item.as_str()).map(|item| item.to_string())),
        retryable: failure
            .and_then(|item| item.get("retryable"))
            .and_then(|item| item.as_bool())
            .unwrap_or(false),
    }
}

fn load_and_migrate_project_doc(
    path: &Path,
    expected_type: &str,
    migrated_any: &mut bool,
    notes: &mut Vec<String>,
) -> Result<Option<Value>, String> {
    if !path.is_file() {
        return Ok(None);
    }

    let raw = std::fs::read_to_string(path)
        .map_err(|e| coded_error("E_PROJECT_DOC_READ_FAILED", format!("无法读取项目文档 {}: {}", path.display(), e)))?;
    let parsed: Value = serde_json::from_str(&raw)
        .map_err(|e| coded_error("E_PROJECT_DOC_INVALID_JSON", format!("项目文档 JSON 无法解析 {}: {}", path.display(), e)))?;
    let (migrated, migrated_value, migration_notes) = migrate_v5_document(parsed, expected_type)?;

    if migrated {
        *migrated_any = true;
        let formatted = serde_json::to_string_pretty(&migrated_value).map_err(|e| {
            coded_error(
                "E_PROJECT_DOC_REWRITE_FAILED",
                format!("无法序列化迁移后的项目文档 {}: {}", path.display(), e),
            )
        })?;
        std::fs::write(path, formatted).map_err(|e| {
            coded_error(
                "E_PROJECT_DOC_REWRITE_FAILED",
                format!("无法写回迁移后的项目文档 {}: {}", path.display(), e),
            )
        })?;
    }

    notes.extend(
        migration_notes
            .into_iter()
            .map(|note| format!("{}: {}", path.file_name().and_then(|v| v.to_str()).unwrap_or(expected_type), note)),
    );

    Ok(Some(migrated_value))
}

fn load_timeline_doc_resilient(
    root: &Path,
    library: &Option<Value>,
    blueprint: &Option<Value>,
    render_plan: &Option<Value>,
    migrated_any: &mut bool,
    notes: &mut Vec<String>,
) -> Result<Option<Value>, String> {
    let timeline_path = root.join("timeline.json");
    if timeline_path.is_file() {
        match load_and_migrate_project_doc(&timeline_path, "timeline", migrated_any, notes) {
            Ok(timeline) => return Ok(timeline),
            Err(error) => {
                *migrated_any = true;
                notes.push(format!(
                    "timeline.json: migration failed, original file kept, using recovered in-memory timeline ({})",
                    error
                ));
                return Ok(build_recovered_timeline_doc(
                    root,
                    library.as_ref(),
                    blueprint.as_ref(),
                    render_plan.as_ref(),
                    false,
                    notes,
                ));
            }
        }
    }

    let recovered = build_recovered_timeline_doc(
        root,
        library.as_ref(),
        blueprint.as_ref(),
        render_plan.as_ref(),
        true,
        notes,
    );
    if recovered.is_some() {
        *migrated_any = true;
    }
    Ok(recovered)
}

fn build_recovered_timeline_doc(
    root: &Path,
    _library: Option<&Value>,
    blueprint: Option<&Value>,
    render_plan: Option<&Value>,
    write_missing_file: bool,
    notes: &mut Vec<String>,
) -> Option<Value> {
    let plan = render_plan?;
    let segments = plan
        .get("segments")
        .and_then(|item| item.as_array())
        .cloned()
        .unwrap_or_default();
    let title = blueprint
        .and_then(|item| item.get("title"))
        .and_then(|item| item.as_str())
        .map(|item| item.to_string());
    let now = unix_timestamp_millis().to_string();
    let mut clip_index = serde_json::Map::new();
    let mut video_clip_ids = Vec::new();
    let mut title_clip_ids = Vec::new();
    let audio_clip_ids: Vec<Value> = Vec::new();

    for (index, segment) in segments.iter().enumerate() {
        let stype = segment
            .get("type")
            .and_then(|item| item.as_str())
            .unwrap_or("image");
        let track_id = if matches!(stype, "title" | "chapter" | "end") {
            "track_title_main"
        } else {
            "track_video_main"
        };
        let clip_id = format!(
            "clip_recovered_{}_{}",
            stype,
            segment
                .get("segment_id")
                .and_then(|item| item.as_str())
                .map(sanitize_timeline_id_part)
                .unwrap_or_else(|| index.to_string())
        );
        let start = segment.get("start_time").and_then(|item| item.as_f64()).unwrap_or_else(|| {
            if index == 0 {
                0.0
            } else {
                segments
                    .get(index - 1)
                    .and_then(|previous| previous.get("end_time"))
                    .and_then(|item| item.as_f64())
                    .unwrap_or(0.0)
            }
        });
        let duration = segment
            .get("duration")
            .and_then(|item| item.as_f64())
            .unwrap_or(3.0)
            .max(0.0);
        let end = segment
            .get("end_time")
            .and_then(|item| item.as_f64())
            .unwrap_or(start + duration);

        if track_id == "track_title_main" {
            title_clip_ids.push(Value::String(clip_id.clone()));
        } else {
            video_clip_ids.push(Value::String(clip_id.clone()));
        }

        clip_index.insert(
            clip_id.clone(),
            json!({
                "clip_id": clip_id,
                "track_id": track_id,
                "kind": if track_id == "track_title_main" { "title_card" } else { stype },
                "enabled": true,
                "locked": false,
                "timeline_start": start,
                "timeline_duration": duration,
                "timeline_end": end,
                "source_in": 0,
                "source_out": duration,
                "playback_rate": 1,
                "source_ref": {
                    "segment_id": segment.get("segment_id").cloned().unwrap_or(Value::Null),
                    "section_id": segment.get("section_id").cloned().unwrap_or(Value::Null),
                    "asset_id": segment.get("asset_id").cloned().unwrap_or(Value::Null),
                    "source_path": segment.get("source_path").cloned().unwrap_or(Value::Null)
                },
                "content": {},
                "presentation": {},
                "invalidation_hint": {
                    "primary_scope": "timeline_compile",
                    "requires_preview_rebuild": true,
                    "requires_final_rebuild": true,
                    "cache_namespace": "timeline"
                },
                "metadata": {
                    "recovered_from": "render_plan",
                    "recovered_at": now.clone()
                }
            }),
        );
    }

    let timeline = json!({
        "schema_version": CURRENT_V5_SCHEMA_VERSION,
        "document_type": "timeline",
        "timeline_version": CURRENT_TIMELINE_VERSION,
        "project_ref": {
            "project_id": format!("project_recovered_{}", sanitize_timeline_id_part(&root.display().to_string())),
            "project_dir": root.display().to_string(),
            "title": title
        },
        "source_ref": {
            "media_library_path": root.join("media_library.json").display().to_string(),
            "story_blueprint_path": root.join("story_blueprint.json").display().to_string(),
            "render_plan_path": root.join("render_plan.json").display().to_string(),
            "generated_from_blueprint": blueprint.is_some(),
            "generated_at": now.clone()
        },
        "tracks": [
            {
                "track_id": "track_video_main",
                "kind": "video",
                "label": "Main Video",
                "order": 0,
                "enabled": !video_clip_ids.is_empty(),
                "locked": false,
                "clip_ids": video_clip_ids
            },
            {
                "track_id": "track_title_main",
                "kind": "title",
                "label": "Titles",
                "order": 1,
                "enabled": !title_clip_ids.is_empty(),
                "locked": false,
                "clip_ids": title_clip_ids
            },
            {
                "track_id": "track_audio_main",
                "kind": "audio",
                "label": "Audio",
                "order": 2,
                "enabled": false,
                "locked": false,
                "clip_ids": audio_clip_ids
            }
        ],
        "clip_index": Value::Object(clip_index),
        "dependency_graph": [],
        "invalidation_rules_version": "timeline_invalidation_v1",
        "performance_policy": {
            "preview": {
                "cache_namespace": "preview",
                "uses_original_source": false,
                "allow_proxy": true
            },
            "final": {
                "cache_namespace": "final",
                "uses_original_source": true,
                "allow_proxy": false
            }
        },
        "metadata": {
            "created_at": now.clone(),
            "updated_at": now,
            "generated_from": "project_recovery",
            "editor_mode": "auto",
            "dirty": false,
            "migration_notes": ["timeline recovered from render_plan"]
        }
    });

    if write_missing_file {
        let timeline_path = root.join("timeline.json");
        match serde_json::to_string_pretty(&timeline)
            .map_err(|e| e.to_string())
            .and_then(|formatted| std::fs::write(&timeline_path, formatted).map_err(|e| e.to_string()))
        {
            Ok(_) => notes.push("timeline.json: generated from render_plan for legacy project".to_string()),
            Err(error) => notes.push(format!(
                "timeline.json: generated in memory but could not be written ({})",
                error
            )),
        }
    } else {
        notes.push("timeline.json: recovered in memory from render_plan without overwriting original".to_string());
    }

    Some(timeline)
}

fn sanitize_timeline_id_part(value: &str) -> String {
    let sanitized = value
        .chars()
        .map(|ch| if ch.is_ascii_alphanumeric() { ch } else { '_' })
        .collect::<String>();
    let trimmed = sanitized.trim_matches('_');
    if trimmed.is_empty() {
        "unknown".to_string()
    } else {
        trimmed.chars().take(48).collect()
    }
}

fn unix_timestamp_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0)
}

fn migrate_v5_document(mut value: Value, expected_type: &str) -> Result<(bool, Value, Vec<String>), String> {
    let obj = value.as_object_mut().ok_or_else(|| {
        coded_error(
            "E_PROJECT_DOC_INVALID_SHAPE",
            format!("项目文档不是有效对象，期望 document_type={}", expected_type),
        )
    })?;

    let actual_type = obj
        .get("document_type")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();
    if actual_type != expected_type {
        return Err(coded_error(
            "E_PROJECT_DOC_TYPE_MISMATCH",
            format!("项目文档类型不匹配：期望 {}，实际 {}", expected_type, actual_type),
        ));
    }

    let mut migrated = false;
    let mut notes = Vec::new();
    let version_before = obj
        .get("schema_version")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown")
        .to_string();

    match expected_type {
        "media_library" => migrate_media_library_doc(obj, &mut migrated, &mut notes),
        "story_blueprint" => migrate_story_blueprint_doc(obj, &mut migrated, &mut notes),
        "render_plan" => migrate_render_plan_doc(obj, &mut migrated, &mut notes),
        "timeline" => migrate_timeline_doc(obj, &mut migrated, &mut notes),
        _ => {}
    }

    if obj
        .get("schema_version")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        != CURRENT_V5_SCHEMA_VERSION
    {
        obj.insert(
            "schema_version".to_string(),
            Value::String(CURRENT_V5_SCHEMA_VERSION.to_string()),
        );
        migrated = true;
        notes.push(format!(
            "schema_version {} -> {}",
            version_before, CURRENT_V5_SCHEMA_VERSION
        ));
    }

    Ok((migrated, value, notes))
}

fn migrate_media_library_doc(
    obj: &mut serde_json::Map<String, Value>,
    migrated: &mut bool,
    notes: &mut Vec<String>,
) {
    ensure_object_child(obj, "project", migrated, notes, "补全 project");
    if let Some(project) = obj.get_mut("project").and_then(|v| v.as_object_mut()) {
        if !project.contains_key("project_title") {
            project.insert("project_title".to_string(), Value::Null);
            *migrated = true;
            notes.push("补全 project.project_title".to_string());
        }
    }

    ensure_array_child(obj, "directory_nodes", migrated, notes, "补全 directory_nodes");
    ensure_array_child(obj, "assets", migrated, notes, "补全 assets");
    ensure_object_child(obj, "summary", migrated, notes, "补全 summary");

    if let Some(assets) = obj.get_mut("assets").and_then(|v| v.as_array_mut()) {
        for asset in assets {
            let Some(asset_obj) = asset.as_object_mut() else { continue };
            sync_alias_field(asset_obj, "thumbnail_path", "thumbnail", migrated, notes, "补全图片缩略图字段");
            sync_alias_field(asset_obj, "thumbnail", "thumbnail_path", migrated, notes, "补全兼容 thumbnail 字段");
            if !asset_obj.contains_key("status") {
                asset_obj.insert("status".to_string(), Value::String("ready".to_string()));
                *migrated = true;
            }
        }
    }
}

fn migrate_story_blueprint_doc(
    obj: &mut serde_json::Map<String, Value>,
    migrated: &mut bool,
    notes: &mut Vec<String>,
) {
    if !obj.contains_key("subtitle") {
        obj.insert("subtitle".to_string(), Value::String(String::new()));
        *migrated = true;
        notes.push("补全 subtitle".to_string());
    }
    ensure_array_child(obj, "sections", migrated, notes, "补全 sections");
    ensure_object_child(obj, "metadata", migrated, notes, "补全 metadata");
    if let Some(metadata) = obj.get_mut("metadata").and_then(|v| v.as_object_mut()) {
        if !metadata.contains_key("chapter_background_mode") {
            metadata.insert(
                "chapter_background_mode".to_string(),
                Value::String("auto_bridge".to_string()),
            );
            *migrated = true;
            notes.push("补全 metadata.chapter_background_mode".to_string());
        }
    }
    if let Some(sections) = obj.get_mut("sections").and_then(|v| v.as_array_mut()) {
        for section in sections {
            migrate_story_section(section, migrated);
        }
    }
}

fn migrate_story_section(value: &mut Value, migrated: &mut bool) {
    let Some(section) = value.as_object_mut() else { return };
    if !section.contains_key("children") {
        section.insert("children".to_string(), Value::Array(Vec::new()));
        *migrated = true;
    }
    if !section.contains_key("asset_refs") {
        section.insert("asset_refs".to_string(), Value::Array(Vec::new()));
        *migrated = true;
    }
    if let Some(children) = section.get_mut("children").and_then(|v| v.as_array_mut()) {
        for child in children {
            migrate_story_section(child, migrated);
        }
    }
}

fn migrate_render_plan_doc(
    obj: &mut serde_json::Map<String, Value>,
    migrated: &mut bool,
    notes: &mut Vec<String>,
) {
    ensure_array_child(obj, "segments", migrated, notes, "补全 segments");
    if !obj.contains_key("output_path") {
        obj.insert("output_path".to_string(), Value::String(String::new()));
        *migrated = true;
        notes.push("补全 output_path".to_string());
    }
    if let Some(segments) = obj.get_mut("segments").and_then(|v| v.as_array_mut()) {
        for segment in segments {
            let Some(seg) = segment.as_object_mut() else { continue };
            if !seg.contains_key("render_route_tags") {
                seg.insert("render_route_tags".to_string(), Value::Array(Vec::new()));
                *migrated = true;
            }
        }
    }
}

fn migrate_timeline_doc(
    obj: &mut serde_json::Map<String, Value>,
    migrated: &mut bool,
    notes: &mut Vec<String>,
) {
    let timeline_version = obj
        .get("timeline_version")
        .and_then(|v| v.as_str())
        .unwrap_or("missing")
        .to_string();
    if timeline_version != CURRENT_TIMELINE_VERSION {
        obj.insert("timeline_version".to_string(), Value::String(CURRENT_TIMELINE_VERSION.to_string()));
        *migrated = true;
        notes.push(format!("timeline_version {} -> {}", timeline_version, CURRENT_TIMELINE_VERSION));
    }
    ensure_object_child(obj, "project_ref", migrated, notes, "timeline: ensure project_ref");
    ensure_object_child(obj, "source_ref", migrated, notes, "timeline: ensure source_ref");
    ensure_array_child(obj, "tracks", migrated, notes, "timeline: ensure tracks");
    ensure_object_child(obj, "clip_index", migrated, notes, "timeline: ensure clip_index");
    ensure_array_child(obj, "dependency_graph", migrated, notes, "timeline: ensure dependency_graph");
    ensure_object_child(obj, "metadata", migrated, notes, "timeline: ensure metadata");
    ensure_object_child(obj, "performance_policy", migrated, notes, "timeline: ensure performance_policy");

    if !obj.contains_key("invalidation_rules_version") {
        obj.insert(
            "invalidation_rules_version".to_string(),
            Value::String("timeline_invalidation_v1".to_string()),
        );
        *migrated = true;
        notes.push("timeline: ensure invalidation_rules_version".to_string());
    }

    if let Some(policy) = obj.get_mut("performance_policy").and_then(|v| v.as_object_mut()) {
        if !policy.get("preview").map(|v| v.is_object()).unwrap_or(false) {
            policy.insert(
                "preview".to_string(),
                json!({
                    "cache_namespace": "preview",
                    "uses_original_source": false,
                    "allow_proxy": true
                }),
            );
            *migrated = true;
            notes.push("timeline: ensure preview performance policy".to_string());
        }
        if !policy.get("final").map(|v| v.is_object()).unwrap_or(false) {
            policy.insert(
                "final".to_string(),
                json!({
                    "cache_namespace": "final",
                    "uses_original_source": true,
                    "allow_proxy": false
                }),
            );
            *migrated = true;
            notes.push("timeline: ensure final performance policy".to_string());
        }
    }

    if let Some(metadata) = obj.get_mut("metadata").and_then(|v| v.as_object_mut()) {
        if !metadata.get("migration_notes").map(|v| v.is_array()).unwrap_or(false) {
            metadata.insert("migration_notes".to_string(), Value::Array(Vec::new()));
            *migrated = true;
            notes.push("timeline: ensure metadata.migration_notes".to_string());
        }
    }
}

fn ensure_object_child(
    obj: &mut serde_json::Map<String, Value>,
    key: &str,
    migrated: &mut bool,
    notes: &mut Vec<String>,
    note: &str,
) {
    if !obj.get(key).map(|v| v.is_object()).unwrap_or(false) {
        obj.insert(key.to_string(), Value::Object(Default::default()));
        *migrated = true;
        notes.push(note.to_string());
    }
}

fn ensure_array_child(
    obj: &mut serde_json::Map<String, Value>,
    key: &str,
    migrated: &mut bool,
    notes: &mut Vec<String>,
    note: &str,
) {
    if !obj.get(key).map(|v| v.is_array()).unwrap_or(false) {
        obj.insert(key.to_string(), Value::Array(Vec::new()));
        *migrated = true;
        notes.push(note.to_string());
    }
}

fn sync_alias_field(
    obj: &mut serde_json::Map<String, Value>,
    primary: &str,
    alias: &str,
    migrated: &mut bool,
    notes: &mut Vec<String>,
    note: &str,
) {
    if !obj.contains_key(primary) {
        if let Some(value) = obj.get(alias).cloned() {
            obj.insert(primary.to_string(), value);
            *migrated = true;
            notes.push(note.to_string());
        }
    }
}

fn clear_job(manager: &JobManager, job_id: &str) {
    if let Ok(mut current) = manager.current.lock() {
        if current.as_ref().map(|job| job.id.as_str()) == Some(job_id) {
            *current = None;
        }
    }
}

fn kill_process_tree(pid: u32) {
    #[cfg(target_os = "windows")]
    {
        let pid = pid.to_string();
        let mut cmd = Command::new("taskkill");
        prepare_hidden_command(&mut cmd);
        let _ = cmd.args(["/PID", &pid, "/T", "/F"]).status();
    }

    #[cfg(not(target_os = "windows"))]
    {
        let pid = pid.to_string();
        let _ = Command::new("kill").args(["-TERM", &pid]).status();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_test_dir(label: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time went backwards")
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "video_create_{}_{}_{}",
            label,
            std::process::id(),
            nonce
        ));
        std::fs::create_dir_all(&path).expect("test directory should be created");
        path
    }

    fn cleanup_test_dir(path: &Path) {
        let _ = std::fs::remove_dir_all(path);
    }

    #[test]
    fn migrate_media_library_adds_compat_fields() {
        let input = json!({
            "schema_version": "5.4",
            "document_type": "media_library",
            "project": {
                "source_root": "D:/demo",
                "scan_time": "2026-01-01T00:00:00Z"
            },
            "assets": [
                {
                    "asset_id": "a1",
                    "type": "image",
                    "relative_path": "a.jpg",
                    "absolute_path": "D:/demo/a.jpg",
                    "thumbnail": "thumb.jpg",
                    "file": {
                        "name": "a.jpg",
                        "extension": ".jpg",
                        "size_bytes": 12,
                        "modified_time": "2026-01-01T00:00:00Z"
                    },
                    "media": {
                        "width": 100,
                        "height": 100,
                        "orientation": "square",
                        "shooting_date": null
                    },
                    "classification": {
                        "directory_node_id": "n1",
                        "city": null,
                        "scenic_spot": null
                    }
                }
            ]
        });

        let (migrated, value, notes) = migrate_v5_document(input, "media_library").expect("migration should succeed");
        assert!(migrated);
        assert!(!notes.is_empty());
        assert_eq!(value["schema_version"], CURRENT_V5_SCHEMA_VERSION);
        assert_eq!(value["project"]["project_title"], Value::Null);
        assert_eq!(value["assets"][0]["thumbnail_path"], "thumb.jpg");
        assert_eq!(value["assets"][0]["status"], "ready");
    }

    #[test]
    fn migrate_story_blueprint_adds_children_and_metadata_defaults() {
        let input = json!({
            "schema_version": "5.3",
            "document_type": "story_blueprint",
            "title": "Demo",
            "strategy": "smart_director",
            "sections": [
                {
                    "section_id": "s1",
                    "section_type": "chapter",
                    "title": "Chapter 1",
                    "subtitle": null,
                    "enabled": true,
                    "source_node_id": null
                }
            ]
        });

        let (migrated, value, _) = migrate_v5_document(input, "story_blueprint").expect("migration should succeed");
        assert!(migrated);
        assert_eq!(value["schema_version"], CURRENT_V5_SCHEMA_VERSION);
        assert_eq!(value["subtitle"], "");
        assert_eq!(value["metadata"]["chapter_background_mode"], "auto_bridge");
        assert!(value["sections"][0]["children"].is_array());
        assert!(value["sections"][0]["asset_refs"].is_array());
    }

    #[test]
    fn migrate_render_plan_type_mismatch_returns_error_code() {
        let input = json!({
            "schema_version": "5.4",
            "document_type": "story_blueprint",
            "title": "Wrong"
        });

        let error = migrate_v5_document(input, "render_plan").expect_err("type mismatch should fail");
        assert!(error.contains("[E_PROJECT_DOC_TYPE_MISMATCH]"));
    }

    #[test]
    fn project_recovery_generates_missing_timeline_from_render_plan() {
        let root = unique_test_dir("timeline_missing_recovery");
        write_project_doc(&root, "media_library.json", json!({
            "schema_version": CURRENT_V5_SCHEMA_VERSION,
            "document_type": "media_library",
            "project": {},
            "assets": [],
            "directory_nodes": [],
            "summary": {}
        }));
        write_project_doc(&root, "story_blueprint.json", json!({
            "schema_version": CURRENT_V5_SCHEMA_VERSION,
            "document_type": "story_blueprint",
            "title": "Recovered Project",
            "subtitle": "",
            "metadata": {},
            "sections": []
        }));
        write_project_doc(&root, "render_plan.json", json!({
            "schema_version": CURRENT_V5_SCHEMA_VERSION,
            "document_type": "render_plan",
            "segments": [
                {
                    "segment_id": "seg_1",
                    "type": "image",
                    "asset_id": "asset_1",
                    "source_path": "image.jpg",
                    "start_time": 0,
                    "duration": 3,
                    "end_time": 3
                }
            ],
            "render_settings": {}
        }));

        let loaded = load_project_documents_v5_blocking(root.display().to_string()).expect("project should load");
        assert!(loaded.migrated);
        assert!(root.join("timeline.json").is_file());
        let timeline = loaded.timeline.expect("timeline should be generated");
        assert_eq!(timeline["document_type"], "timeline");
        assert_eq!(timeline["timeline_version"], CURRENT_TIMELINE_VERSION);
        assert_eq!(timeline["metadata"]["generated_from"], "project_recovery");
        assert!(loaded.migration_notes.iter().any(|note| note.contains("generated from render_plan")));

        cleanup_test_dir(&root);
    }

    #[test]
    fn project_recovery_keeps_invalid_timeline_and_uses_memory_recovery() {
        let root = unique_test_dir("timeline_invalid_recovery");
        write_project_doc(&root, "media_library.json", json!({
            "schema_version": CURRENT_V5_SCHEMA_VERSION,
            "document_type": "media_library",
            "project": {},
            "assets": [],
            "directory_nodes": [],
            "summary": {}
        }));
        write_project_doc(&root, "story_blueprint.json", json!({
            "schema_version": CURRENT_V5_SCHEMA_VERSION,
            "document_type": "story_blueprint",
            "title": "Recovered Project",
            "subtitle": "",
            "metadata": {},
            "sections": []
        }));
        write_project_doc(&root, "render_plan.json", json!({
            "schema_version": CURRENT_V5_SCHEMA_VERSION,
            "document_type": "render_plan",
            "segments": [
                { "segment_id": "seg_1", "type": "image", "duration": 2 }
            ],
            "render_settings": {}
        }));
        let invalid_path = root.join("timeline.json");
        std::fs::write(&invalid_path, "{ invalid timeline").expect("invalid timeline should be written");

        let loaded = load_project_documents_v5_blocking(root.display().to_string()).expect("project should recover");
        assert!(loaded.migrated);
        assert_eq!(
            std::fs::read_to_string(&invalid_path).expect("invalid timeline should remain"),
            "{ invalid timeline"
        );
        let timeline = loaded.timeline.expect("in-memory timeline should be returned");
        assert_eq!(timeline["document_type"], "timeline");
        assert!(loaded.migration_notes.iter().any(|note| note.contains("original file kept")));

        cleanup_test_dir(&root);
    }

    fn write_project_doc(root: &Path, name: &str, value: Value) {
        std::fs::write(
            root.join(name),
            serde_json::to_string_pretty(&value).expect("project JSON should serialize"),
        )
        .expect("project doc should be written");
    }

    #[test]
    fn failure_regression_render_plan_sources_handles_chinese_paths_and_missing_assets() {
        let root = unique_test_dir("失败回归_中文路径");
        let source_dir = root.join("素材").join("泉州").join("西街");
        std::fs::create_dir_all(&source_dir).expect("source directory should exist");

        let existing_asset = source_dir.join("镜头1.jpg");
        std::fs::write(&existing_asset, b"image").expect("asset should be written");
        let missing_asset = source_dir.join("镜头2.jpg");
        let plan_path = root.join("render_plan.json");
        std::fs::write(
            &plan_path,
            serde_json::to_string_pretty(&json!({
                "document_type": "render_plan",
                "schema_version": CURRENT_V5_SCHEMA_VERSION,
                "segments": [
                    { "source_path": existing_asset.display().to_string() },
                    { "source_path": missing_asset.display().to_string() }
                ]
            }))
            .expect("plan JSON should serialize"),
        )
        .expect("plan should be written");

        let check = check_render_plan_sources(&plan_path);
        assert!(!check.ok);
        assert_eq!(check.code.as_deref(), Some("E_MEDIA_SOURCE_MISSING"));
        assert!(
            check.detail.as_deref().unwrap_or_default().contains("镜头2.jpg"),
            "missing Chinese path should be surfaced in diagnostics"
        );

        cleanup_test_dir(&root);
    }

    #[test]
    fn failure_regression_render_plan_invalid_json_reports_code() {
        let root = unique_test_dir("失败回归_render_plan_invalid");
        let plan_path = root.join("render_plan.json");
        std::fs::write(&plan_path, "{ invalid json").expect("plan should be written");

        let check = check_render_plan_sources(&plan_path);
        assert!(!check.ok);
        assert_eq!(check.code.as_deref(), Some("E_RENDER_PLAN_INVALID_JSON"));

        cleanup_test_dir(&root);
    }

    #[test]
    fn failure_regression_output_target_rejects_non_directory_parent() {
        let root = unique_test_dir("失败回归_output_parent");
        let fake_dir = root.join("not_a_directory");
        std::fs::write(&fake_dir, b"blocker").expect("file blocker should be written");
        let output_path = fake_dir.join("final.mp4");

        let check = check_output_target(&output_path);
        assert!(!check.ok);
        assert_eq!(check.code.as_deref(), Some("E_OUTPUT_NOT_WRITABLE"));

        cleanup_test_dir(&root);
    }

    #[test]
    fn failure_regression_preflight_reports_unwritable_output_dir() {
        let root = unique_test_dir("失败回归_preflight_output");
        let input_dir = root.join("input");
        std::fs::create_dir_all(&input_dir).expect("input directory should exist");

        let output_dir = root.join("locked_output");
        std::fs::write(&output_dir, b"not a directory").expect("output blocker should be written");

        let plan_path = root.join("render_plan.json");
        std::fs::write(
            &plan_path,
            serde_json::to_string_pretty(&json!({
                "document_type": "render_plan",
                "schema_version": CURRENT_V5_SCHEMA_VERSION,
                "segments": []
            }))
            .expect("plan JSON should serialize"),
        )
        .expect("plan should be written");

        let output_path = root.join("final.mp4");
        let diagnostics = preflight_render_v5_blocking(
            input_dir.display().to_string(),
            output_dir.display().to_string(),
            plan_path.display().to_string(),
            output_path.display().to_string(),
        )
        .expect("preflight should return diagnostics");

        assert!(!diagnostics.ok);
        assert_eq!(diagnostics.code.as_deref(), Some("E_PREFLIGHT_CHECK_FAILED"));
        assert!(diagnostics.checks.iter().any(|check| {
            check.id == "output_dir" && check.code.as_deref() == Some("E_DIRECTORY_NOT_WRITABLE")
        }));

        cleanup_test_dir(&root);
    }

    #[test]
    fn failure_regression_worker_entrypoint_missing_returns_error_code() {
        let error = resolve_worker_launch_spec(Vec::new(), None)
            .expect_err("missing worker entrypoint should fail");
        assert!(error.contains("[E_WORKER_ENTRYPOINT_MISSING]"));
    }

    #[test]
    fn project_state_roundtrip_reads_back_saved_payload() {
        let root = unique_test_dir("project_state_roundtrip");
        let payload = r#"{"savedAt":"2026-05-27T10:00:00.000Z","data":{"phase":"render"}}"#;

        save_project_state_blocking(root.display().to_string(), payload.to_string())
            .expect("project state should save");
        let loaded = load_project_state_blocking(root.display().to_string())
            .expect("project state should load");

        assert_eq!(loaded.as_deref(), Some(payload));
        cleanup_test_dir(&root);
    }

    #[test]
    fn project_state_missing_file_returns_none() {
        let root = unique_test_dir("project_state_missing");
        let loaded = load_project_state_blocking(root.display().to_string())
            .expect("missing project state should not fail");
        assert!(loaded.is_none());
        cleanup_test_dir(&root);
    }

    #[test]
    fn project_state_requires_non_empty_project_dir() {
        let error = save_project_state_blocking("   ".to_string(), "{}".to_string())
            .expect_err("blank project dir should fail");
        assert!(error.contains("[E_PROJECT_STATE_DIR_REQUIRED]"));
    }

    #[test]
    fn build_report_summary_extracts_resume_recovery_fields() {
        let root = unique_test_dir("build_report_summary_resume");
        std::fs::write(
            root.join("build_report.json"),
            serde_json::to_string_pretty(&json!({
                "status": "failed",
                "render_intent": "final",
                "render_mode": "v5.6_long_video_stable",
                "failed_stage": "chunk_render",
                "output_path": root.join("final.mp4").display().to_string(),
                "selected_backend": "stable_chunked",
                "actual_backend": "ffmpeg_stable_backend",
                "backend_reason": "stable_renderer_selected",
                "fallback_chain": ["ffmpeg_stable_backend", "legacy_moviepy_backend"],
                "fallback_used": "legacy_moviepy_backend",
                "fallback_reason": "concat_failed",
                "fallback_applied": true,
                "chunk_count": 6,
                "segment_fast_path_rate": 0.75,
                "chunk_fast_path_rate": 0.5,
                "segment_route_difference_count": 2,
                "segment_route_difference_rate": 0.3333,
                "created_at": "2026-05-27T10:30:00",
                "failure": {
                    "code": "chunk_render_failed",
                    "message": "chunk_003 failed",
                    "retryable": true
                },
                "recovery": {
                    "resumable": true,
                    "resumed_from_manifest": true,
                    "manifest_path": root.join("chunks").join("chunk_manifest.json").display().to_string(),
                    "reused_chunk_count": 2,
                    "completed_chunk_count": 4,
                    "failed_chunk_count": 1,
                    "reported_chunk_count": 5,
                    "failed_chunk": "chunk_003.mp4"
                }
            }))
            .expect("report JSON should serialize"),
        )
        .expect("report should be written");

        let summary = load_build_report_summary_blocking(root.display().to_string())
            .expect("build report should load");
        assert_eq!(summary.status.as_deref(), Some("failed"));
        assert_eq!(summary.render_intent.as_deref(), Some("final"));
        assert_eq!(summary.failed_stage.as_deref(), Some("chunk_render"));
        assert_eq!(summary.actual_backend.as_deref(), Some("ffmpeg_stable_backend"));
        assert_eq!(summary.fallback_used.as_deref(), Some("legacy_moviepy_backend"));
        assert!(summary.fallback_applied);
        assert_eq!(summary.segment_route_difference_count, 2);
        assert!(summary.resumable);
        assert!(summary.resumed_from_manifest);
        assert_eq!(summary.reused_chunk_count, 2);
        assert_eq!(summary.completed_chunk_count, 4);
        assert_eq!(summary.failed_chunk.as_deref(), Some("chunk_003.mp4"));
        assert_eq!(summary.failure_code.as_deref(), Some("chunk_render_failed"));
        assert!(summary.retryable);

        cleanup_test_dir(&root);
    }

    #[test]
    fn build_report_summary_missing_file_returns_error_code() {
        let root = unique_test_dir("build_report_summary_missing");
        let error = load_build_report_summary_blocking(root.display().to_string())
            .expect_err("missing report should fail");
        assert!(error.contains("[E_BUILD_REPORT_MISSING]"));
        cleanup_test_dir(&root);
    }

    #[test]
    fn build_report_summary_invalid_json_returns_error_code() {
        let root = unique_test_dir("build_report_summary_invalid");
        std::fs::write(root.join("build_report.json"), "{ invalid json")
            .expect("broken report should be written");
        let error = load_build_report_summary_blocking(root.display().to_string())
            .expect_err("invalid report should fail");
        assert!(error.contains("[E_BUILD_REPORT_INVALID_JSON]"));
        cleanup_test_dir(&root);
    }

    #[test]
    fn telemetry_starting_new_session_marks_previous_active_session_as_crash() {
        let mut store = TelemetryStore::default();
        let (_first_session, first_recovered) = telemetry_start_session(&mut store, true);
        assert!(!first_recovered);
        let (_second_session, second_recovered) = telemetry_start_session(&mut store, true);
        assert!(second_recovered);
        assert_eq!(store.summary.sessions_started, 2);
        assert_eq!(store.summary.sessions_crashed, 1);
    }

    #[test]
    fn telemetry_records_first_export_only_once_per_session() {
        let mut store = TelemetryStore::default();
        let (session_id, _) = telemetry_start_session(&mut store, true);
        let session_id = session_id.expect("session id should exist");

        telemetry_record_event(
            &mut store,
            TelemetryEventPayload {
                session_id: Some(session_id.clone()),
                event_type: "render_result".to_string(),
                success: Some(false),
                first_export: Some(true),
                error_code: Some("E_MEDIA_SOURCE_MISSING".to_string()),
                support_queue: Some("render-recovery".to_string()),
                severity: Some("warning".to_string()),
                tags: Some(vec!["resumable".to_string()]),
                recovery_resumable: Some(true),
                recovery_retryable: Some(true),
                recovery_completed_chunks: Some(4),
                recovery_reused_chunks: Some(2),
                timestamp: Some("1".to_string()),
            },
        );
        telemetry_record_event(
            &mut store,
            TelemetryEventPayload {
                session_id: Some(session_id),
                event_type: "render_result".to_string(),
                success: Some(true),
                first_export: Some(true),
                error_code: None,
                support_queue: Some("render-recovery".to_string()),
                severity: Some("info".to_string()),
                tags: Some(vec!["retryable".to_string()]),
                recovery_resumable: Some(false),
                recovery_retryable: Some(false),
                recovery_completed_chunks: Some(0),
                recovery_reused_chunks: Some(0),
                timestamp: Some("2".to_string()),
            },
        );

        assert_eq!(store.summary.render_attempts, 2);
        assert_eq!(store.summary.render_successes, 1);
        assert_eq!(store.summary.render_failures, 1);
        assert_eq!(store.summary.first_export_sessions, 1);
        assert_eq!(store.summary.first_export_successes, 0);
    }

    #[test]
    fn telemetry_clear_history_resets_counters_but_preserves_active_session() {
        let mut store = TelemetryStore::default();
        let (session_id, _) = telemetry_start_session(&mut store, true);
        let session_id = session_id.expect("session id should exist");

        telemetry_record_event(
            &mut store,
            TelemetryEventPayload {
                session_id: Some(session_id),
                event_type: "render_result".to_string(),
                success: Some(true),
                first_export: Some(true),
                error_code: None,
                support_queue: Some("general-triage".to_string()),
                severity: Some("info".to_string()),
                tags: Some(vec!["render-success".to_string()]),
                recovery_resumable: Some(false),
                recovery_retryable: Some(false),
                recovery_completed_chunks: Some(0),
                recovery_reused_chunks: Some(0),
                timestamp: Some("3".to_string()),
            },
        );

        telemetry_clear_history(&mut store);

        assert_eq!(store.summary.render_attempts, 0);
        assert_eq!(store.summary.first_export_sessions, 0);
        assert!(store.recent_events.is_empty());
        assert_eq!(store.summary.sessions_started, 1);
        assert_eq!(
            store
                .active_session
                .as_ref()
                .map(|session| session.first_export_recorded),
            Some(false)
        );
    }

    #[test]
    fn telemetry_settings_reject_non_https_remote_endpoint() {
        let mut store = TelemetryStore::default();
        let error = apply_telemetry_settings(
            &mut store,
            TelemetrySettingsPayload {
                consent_accepted_version: Some(TELEMETRY_CONSENT_VERSION.to_string()),
                remote_upload_enabled: Some(true),
                remote_endpoint: Some("http://example.com/collect".to_string()),
            },
        )
        .expect_err("non-https remote endpoint should be rejected");
        assert!(error.contains("[E_TELEMETRY_REMOTE_ENDPOINT_INVALID]"));
    }

    #[test]
    fn telemetry_event_is_queued_for_remote_upload_when_enabled() {
        let mut store = TelemetryStore::default();
        let (session_id, _) = telemetry_start_session(&mut store, true);
        apply_telemetry_settings(
            &mut store,
            TelemetrySettingsPayload {
                consent_accepted_version: Some(TELEMETRY_CONSENT_VERSION.to_string()),
                remote_upload_enabled: Some(true),
                remote_endpoint: Some("https://telemetry.example.com/collect".to_string()),
            },
        )
        .expect("settings should be accepted");

        telemetry_record_event(
            &mut store,
            TelemetryEventPayload {
                session_id,
                event_type: "frontend_crash".to_string(),
                success: Some(false),
                error_code: Some("E_APP_RUNTIME".to_string()),
                support_queue: Some("app-runtime".to_string()),
                severity: Some("high".to_string()),
                tags: Some(vec!["frontend-runtime".to_string()]),
                recovery_resumable: Some(false),
                recovery_retryable: Some(false),
                recovery_completed_chunks: Some(0),
                recovery_reused_chunks: Some(0),
                first_export: Some(false),
                timestamp: Some("4".to_string()),
            },
        );

        assert_eq!(store.remote.pending_events.len(), 1);
        assert_eq!(
            store.remote.pending_events[0].consent_version,
            TELEMETRY_CONSENT_VERSION.to_string()
        );
    }
}

pub fn run() {
    tauri::Builder::default()
        .manage(JobManager::default())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            startup_self_check,
            preflight_render_v5,
            save_session_snapshot,
            load_session_snapshot,
            clear_session_snapshot,
            save_project_state,
            load_project_state,
            export_diagnostic_bundle,
            load_project_documents_v5,
            load_build_report_summary,
            start_telemetry_session,
            finish_telemetry_session,
            record_telemetry_event,
            load_telemetry_summary,
            clear_telemetry_history,
            update_telemetry_settings,
            flush_remote_telemetry_queue,
            cancel_video,
            open_in_explorer,
            scan_v5,
            plan_v5,
            save_blueprint_v5,
            save_timeline_v5,
            compile_v5,
            timeline_generate_v5,
            timeline_compile_v5,
            timeline_preview_manifest_v5,
            timeline_preview_assets_v5,
            preview_title_v5,
            preview_render_v5,
            render_v5
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
