use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Clone, Default)]
struct JobManager {
    current: Arc<Mutex<Option<ActiveJob>>>,
}

#[derive(Clone)]
struct ActiveJob {
    id: String,
    pid: u32,
    cancelled: Arc<AtomicBool>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct GenerateVideoPayload {
    job_id: Option<String>,
    input_paths: Vec<String>,
    output_dir: String,
    title: String,
    title_subtitle: String,
    end_text: String,
    output_name: String,
    aspect_ratio: String,
    quality: String,
    watermark: String,
    recursive: bool,
    chapters_from_dirs: bool,
    cover: bool,
    render_engine: String,
    dry_run: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GenerateVideoResult {
    ok: bool,
    message: String,
    command_preview: String,
    output_path: Option<String>,
    output_dir: Option<String>,
    cancelled: bool,
    is_dry_run: bool,
}

#[tauri::command]
async fn generate_video(
    app: AppHandle,
    manager: State<'_, JobManager>,
    payload: GenerateVideoPayload,
) -> Result<GenerateVideoResult, String> {
    let manager = manager.inner().clone();

    match tauri::async_runtime::spawn_blocking(move || {
        generate_video_blocking(app, manager, payload)
    })
    .await
    {
        Ok(result) => Ok(result),
        Err(e) => Ok(GenerateVideoResult {
            ok: false,
            message: format!("后台生成任务异常结束: {}", e),
            command_preview: String::new(),
            output_path: None,
            output_dir: None,
            cancelled: false,
            is_dry_run: false,
        }),
    }
}

/// Legacy V3 path.
///
/// V5 主流程已经迁移到 scan_v5 / plan_v5 / compile_v5 / render_v5。
/// 这个命令保留给旧版“一键生成视频”兼容模式。
fn generate_video_blocking(
    app: AppHandle,
    manager: JobManager,
    payload: GenerateVideoPayload,
) -> GenerateVideoResult {
    let script_path = match find_generator_script(&app) {
        Ok(path) => path,
        Err(message) => {
            return GenerateVideoResult {
                ok: false,
                command_preview: build_command_preview(&payload, None, None),
                message,
                output_path: None,
                output_dir: None,
                cancelled: false,
                is_dry_run: payload.dry_run,
            };
        }
    };

    let input = payload
        .input_paths
        .first()
        .cloned()
        .unwrap_or_else(|| ".".to_string());

    if !payload.dry_run && payload.output_dir.is_empty() {
        return GenerateVideoResult {
            ok: false,
            command_preview: build_command_preview(&payload, Some(&script_path), None),
            message: "请选择输出目录。".to_string(),
            output_path: None,
            output_dir: None,
            cancelled: false,
            is_dry_run: payload.dry_run,
        };
    }

    let (output_dir, output_file) = build_output_paths(&payload);
    let command_preview = build_command_preview(
        &payload,
        Some(&script_path),
        if payload.output_dir.is_empty() {
            None
        } else {
            Some(&output_dir)
        },
    );

    if let Err(message) = check_python_environment() {
        return GenerateVideoResult {
            ok: false,
            message,
            command_preview,
            output_path: None,
            output_dir: Some(output_dir.display().to_string()),
            cancelled: false,
            is_dry_run: payload.dry_run,
        };
    }

    if manager.current.lock().map(|job| job.is_some()).unwrap_or(true) {
        return GenerateVideoResult {
            ok: false,
            message: "已有视频正在生成，请先等待完成或停止当前任务。".to_string(),
            command_preview,
            output_path: None,
            output_dir: Some(output_dir.display().to_string()),
            cancelled: false,
            is_dry_run: payload.dry_run,
        };
    }

    let mut cmd = Command::new("python");
    prepare_python_command(&mut cmd);
    cmd.arg(&script_path);
    if let Some(script_dir) = script_path.parent() {
        cmd.current_dir(script_dir);
    }
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    cmd.arg("--input_folder").arg(&input);
    if !payload.output_dir.is_empty() {
        cmd.arg("--output_dir").arg(&output_dir);
    }

    if payload.recursive {
        cmd.arg("--recursive");
    }

    if payload.chapters_from_dirs {
        cmd.arg("--chapters_from_dirs");
    }

    if !payload.title.is_empty() {
        cmd.arg("--title").arg(&payload.title);
    }

    if !payload.title_subtitle.is_empty() {
        cmd.arg("--title_subtitle").arg(&payload.title_subtitle);
    }

    if !payload.end_text.is_empty() {
        cmd.arg("--end").arg(&payload.end_text);
    }

    if !payload.watermark.is_empty() {
        cmd.arg("--watermark").arg(&payload.watermark);
    }

    cmd.arg("--quality").arg(to_python_quality(&payload.quality));
    cmd.arg("--engine").arg(&payload.render_engine);
    cmd.arg("--ratio").arg(&payload.aspect_ratio);

    if payload.cover {
        cmd.arg("--cover");
    }

    if !payload.output_name.is_empty() {
        cmd.arg("--output_name").arg(&payload.output_name);
    }

    if payload.dry_run {
        cmd.arg("--dry_run");
    }

    match cmd.spawn() {
        Ok(mut child) => {
            let job_id = payload
                .job_id
                .clone()
                .unwrap_or_else(|| format!("job-{}", child.id()));
            let cancelled = Arc::new(AtomicBool::new(false));
            let pid = child.id();

            if let Ok(mut current) = manager.current.lock() {
                if current.is_some() {
                    kill_process_tree(pid);
                    return GenerateVideoResult {
                        ok: false,
                        message: "已有视频正在生成，请先等待完成或停止当前任务。".to_string(),
                        command_preview,
                        output_path: None,
                        output_dir: Some(output_dir.display().to_string()),
                        cancelled: false,
                        is_dry_run: payload.dry_run,
                    };
                }

                *current = Some(ActiveJob {
                    id: job_id.clone(),
                    pid,
                    cancelled: cancelled.clone(),
                });
            }

            pipe_child_output_to_frontend(&app, &mut child);

            let status = match child.wait() {
                Ok(status) => status,
                Err(e) => {
                    clear_job(&manager, &job_id);
                    return GenerateVideoResult {
                        ok: false,
                        message: format!("等待 Python 进程结束时失败: {}", e),
                        command_preview,
                        output_path: None,
                        output_dir: Some(output_dir.display().to_string()),
                        cancelled: false,
                        is_dry_run: payload.dry_run,
                    };
                }
            };

            let was_cancelled = cancelled.load(Ordering::SeqCst);
            clear_job(&manager, &job_id);

            if was_cancelled {
                GenerateVideoResult {
                    ok: false,
                    message: "已停止当前视频生成任务。".to_string(),
                    command_preview,
                    output_path: None,
                    output_dir: Some(output_dir.display().to_string()),
                    cancelled: true,
                    is_dry_run: payload.dry_run,
                }
            } else if status.success() && payload.dry_run {
                GenerateVideoResult {
                    ok: true,
                    message: "素材预检完成，素材状态良好。".to_string(),
                    command_preview,
                    output_path: None,
                    output_dir: if payload.output_dir.is_empty() {
                        None
                    } else {
                        Some(output_dir.display().to_string())
                    },
                    cancelled: false,
                    is_dry_run: true,
                }
            } else if status.success() && output_file.is_file() {
                GenerateVideoResult {
                    ok: true,
                    message: format!("视频生成成功：{}", output_file.display()),
                    command_preview,
                    output_path: Some(output_file.display().to_string()),
                    output_dir: Some(output_dir.display().to_string()),
                    cancelled: false,
                    is_dry_run: false,
                }
            } else if status.success() {
                GenerateVideoResult {
                    ok: false,
                    message: format!("脚本已结束，但没有找到总视频文件：{}", output_file.display()),
                    command_preview,
                    output_path: Some(output_file.display().to_string()),
                    output_dir: Some(output_dir.display().to_string()),
                    cancelled: false,
                    is_dry_run: false,
                }
            } else {
                GenerateVideoResult {
                    ok: false,
                    message: format!("执行失败，退出状态: {}", status),
                    command_preview,
                    output_path: None,
                    output_dir: Some(output_dir.display().to_string()),
                    cancelled: false,
                    is_dry_run: payload.dry_run,
                }
            }
        }
        Err(e) => GenerateVideoResult {
            ok: false,
            message: format!("无法启动 Python 进程: {}", e),
            command_preview,
            output_path: None,
            output_dir: Some(output_dir.display().to_string()),
            cancelled: false,
            is_dry_run: payload.dry_run,
        },
    }
}

#[tauri::command]
fn cancel_video(manager: State<'_, JobManager>, job_id: String) -> GenerateVideoResult {
    let job = manager
        .current
        .lock()
        .ok()
        .and_then(|current| current.clone());

    let Some(job) = job else {
        return GenerateVideoResult {
            ok: false,
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

    GenerateVideoResult {
        ok: true,
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
    input_folder: String,
    project_dir: Option<String>,
    recursive: Option<bool>,
) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let script_path = find_v5_engine_script(&app)?;
        let workspace = project_workspace(&input_folder, project_dir)?;
        std::fs::create_dir_all(&workspace)
            .map_err(|e| format!("无法创建 V5 项目目录 {}: {}", workspace.display(), e))?;
        let output_path = workspace.join("media_library.json");

        let mut args = vec![
            "scan".to_string(),
            "--input_folder".to_string(),
            input_folder.clone(),
            "--output".to_string(),
            output_path.display().to_string(),
        ];
        if recursive.unwrap_or(true) {
            args.push("--recursive".to_string());
        }

        run_python_to_json_file(&script_path, &args, &output_path, "扫描失败")
    })
    .await
    .map_err(|e| format!("V5 scan 后台任务异常: {}", e))?
}

#[tauri::command]
async fn plan_v5(
    app: AppHandle,
    library_path: String,
    output_path: Option<String>,
) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let script_path = find_v5_engine_script(&app)?;
        let lib_path = PathBuf::from(&library_path);
        let output_path = output_path
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                lib_path
                    .parent()
                    .unwrap_or_else(|| Path::new("."))
                    .join("story_blueprint.json")
            });

        let args = vec![
            "plan".to_string(),
            "--library".to_string(),
            library_path.clone(),
            "--output".to_string(),
            output_path.display().to_string(),
        ];

        run_python_to_json_file(&script_path, &args, &output_path, "生成蓝图失败")
    })
    .await
    .map_err(|e| format!("V5 plan 后台任务异常: {}", e))?
}

#[tauri::command]
async fn save_blueprint_v5(path: String, content: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let target = PathBuf::from(path);
        if let Some(parent) = target.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("无法创建蓝图目录: {}", e))?;
        }
        std::fs::write(&target, content).map_err(|e| format!("无法保存蓝图: {}", e))
    })
    .await
    .map_err(|e| format!("保存蓝图后台任务异常: {}", e))?
}

#[tauri::command]
async fn compile_v5(
    app: AppHandle,
    blueprint_path: String,
    library_path: String,
    output_path: Option<String>,
) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let script_path = find_v5_engine_script(&app)?;
        let bp_path = PathBuf::from(&blueprint_path);
        let output_path = output_path
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                bp_path
                    .parent()
                    .unwrap_or_else(|| Path::new("."))
                    .join("render_plan.json")
            });

        let args = vec![
            "compile".to_string(),
            "--blueprint".to_string(),
            blueprint_path.clone(),
            "--library".to_string(),
            library_path.clone(),
            "--output".to_string(),
            output_path.display().to_string(),
        ];

        run_python_to_json_file(&script_path, &args, &output_path, "编译渲染计划失败")
    })
    .await
    .map_err(|e| format!("V5 compile 后台任务异常: {}", e))?
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
        render_v5_blocking(app, manager, plan_path, output_path, params_json, job_id)
    })
    .await
    .map_err(|e| format!("V5 render 后台任务异常: {}", e))?
}

#[tauri::command]
async fn preview_title_v5(
    app: AppHandle,
    title: String,
    subtitle: Option<String>,
    style_json: String,
    aspect_ratio: Option<String>,
    background: Option<String>,
) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let script_path = find_v5_engine_script(&app)?;
        let mut output_dir = app.path().app_cache_dir().unwrap_or_else(|_| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("scratch")
        });
        output_dir.push("title_previews");
        std::fs::create_dir_all(&output_dir)
            .map_err(|e| format!("æ— æ³•åˆ›å»ºé¢„è§ˆç¼“å­˜ç›®å½• {}: {}", output_dir.display(), e))?;

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

        let args = vec![
            "preview-title".to_string(),
            "--title".to_string(),
            title,
            "--subtitle".to_string(),
            subtitle,
            "--style_json".to_string(),
            style_json,
            "--output".to_string(),
            output_path.display().to_string(),
            "--aspect_ratio".to_string(),
            aspect_ratio,
            "--background".to_string(),
            background,
            "--duration".to_string(),
            "3.0".to_string(),
        ];

        run_python_preview_command(&script_path, &args, &output_path)
    })
    .await
    .map_err(|e| format!("V5 title preview åŽå°ä»»åŠ¡å¼‚å¸¸: {}", e))?
}

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

fn project_workspace(input_folder: &str, project_dir: Option<String>) -> Result<PathBuf, String> {
    if let Some(dir) = project_dir {
        if !dir.trim().is_empty() {
            return Ok(PathBuf::from(dir));
        }
    }
    Ok(PathBuf::from(input_folder).join(".video_create_project"))
}

fn run_python_to_json_file(
    script_path: &Path,
    args: &[String],
    output_path: &Path,
    error_prefix: &str,
) -> Result<String, String> {
    let mut cmd = Command::new("python");
    prepare_python_command(&mut cmd);
    cmd.arg(script_path).args(args);

    if let Some(script_dir) = script_path.parent() {
        cmd.current_dir(script_dir);
    }

    let output = cmd
        .output()
        .map_err(|e| format!("启动 V5 引擎失败: {}", e))?;

    if !output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "{}: {}\n{}",
            error_prefix,
            stderr.trim(),
            stdout.trim()
        ));
    }

    let content = std::fs::read_to_string(output_path)
        .map_err(|e| format!("无法读取生成文件 {}: {}", output_path.display(), e))?;

    Ok(content)
}

fn run_python_preview_command(
    script_path: &Path,
    args: &[String],
    output_path: &Path,
) -> Result<String, String> {
    let mut cmd = Command::new("python");
    prepare_python_command(&mut cmd);
    cmd.arg(script_path).args(args);

    if let Some(script_dir) = script_path.parent() {
        cmd.current_dir(script_dir);
    }

    let output = cmd
        .output()
        .map_err(|e| format!("å¯åŠ¨ V5 é¢„è§ˆå¼•æ“Žå¤±è´¥: {}", e))?;

    if !output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "ç”ŸæˆçœŸå®žé¢„è§ˆå¤±è´¥: {}\n{}",
            stderr.trim(),
            stdout.trim()
        ));
    }

    if !output_path.is_file() {
        return Err(format!(
            "é¢„è§ˆå¼•æ“Žå·²ç»“æŸï¼Œä½†æ²¡æœ‰æ‰¾åˆ°è¾“å‡ºæ–‡ä»¶: {}",
            output_path.display()
        ));
    }

    Ok(output_path.display().to_string())
}

fn stable_hash(value: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    value.hash(&mut hasher);
    hasher.finish()
}

fn pipe_child_output_to_frontend(app: &AppHandle, child: &mut std::process::Child) {
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
}

fn build_command_preview(
    payload: &GenerateVideoPayload,
    script_path: Option<&Path>,
    output_dir: Option<&Path>,
) -> String {
    let input = payload
        .input_paths
        .first()
        .cloned()
        .unwrap_or_else(|| "<素材文件夹>".to_string());

    let mut args = vec![
        "python".to_string(),
        quote(
            &script_path
                .map(|path| path.display().to_string())
                .unwrap_or_else(|| "make_bilibili_video_v3.py".to_string()),
        ),
        "--input_folder".to_string(),
        quote(&input),
    ];

    if let Some(output_dir) = output_dir {
        args.extend([
            "--output_dir".to_string(),
            quote(&output_dir.display().to_string()),
        ]);
    }

    if payload.recursive {
        args.push("--recursive".to_string());
    }

    if payload.chapters_from_dirs {
        args.push("--chapters_from_dirs".to_string());
    }

    args.extend([
        "--title".to_string(),
        quote(&payload.title),
        "--title_subtitle".to_string(),
        quote(&payload.title_subtitle),
    ]);

    if !payload.end_text.is_empty() {
        args.extend(["--end".to_string(), quote(&payload.end_text)]);
    }

    if !payload.watermark.is_empty() {
        args.extend(["--watermark".to_string(), quote(&payload.watermark)]);
    }

    args.extend([
        "--quality".to_string(),
        to_python_quality(&payload.quality).to_string(),
        "--engine".to_string(),
        payload.render_engine.clone(),
        "--ratio".to_string(),
        payload.aspect_ratio.clone(),
    ]);

    if payload.cover {
        args.push("--cover".to_string());
    }

    if payload.dry_run {
        args.push("--dry_run".to_string());
    }

    args.extend(["--output_name".to_string(), quote(&payload.output_name)]);
    args.join(" ")
}

fn quote(value: &str) -> String {
    format!("\"{}\"", value.replace('"', "\\\""))
}

fn to_python_quality(quality: &str) -> &str {
    match quality {
        "draft" => "normal",
        "standard" => "high",
        "high" => "ultra",
        other => other,
    }
}

fn build_output_paths(payload: &GenerateVideoPayload) -> (PathBuf, PathBuf) {
    let output_dir = PathBuf::from(&payload.output_dir);
    let output_name = if payload.output_name.is_empty() {
        "bilibili_travel_video"
    } else {
        &payload.output_name
    };

    let output_file = output_dir.join(format!(
        "{}_{}.mp4",
        output_name,
        payload.aspect_ratio.replace(':', "x")
    ));

    (output_dir, output_file)
}

fn check_python_environment() -> Result<(), String> {
    let code = r#"
import importlib.util
import json
import sys

checks = [
    ("numpy", "numpy"),
    ("Pillow", "PIL"),
    ("moviepy", "moviepy.editor"),
    ("imageio-ffmpeg", "imageio_ffmpeg"),
    ("proglog", "proglog"),
]
missing = []
for name, module in checks:
    if importlib.util.find_spec(module) is None:
        missing.append(name)
        continue
    try:
        __import__(module)
    except Exception:
        missing.append(name)

ffmpeg = None
try:
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass

print(json.dumps({
    "ok": not missing and bool(ffmpeg),
    "missing": missing,
    "ffmpeg": ffmpeg,
    "python": sys.executable,
}, ensure_ascii=False))

sys.exit(0 if not missing and ffmpeg else 1)
"#;

    let output = match Command::new("python")
        .arg("-c")
        .arg(code)
        .env("PYTHONIOENCODING", "utf-8")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
    {
        Ok(output) => output,
        Err(e) => {
            return Err(format!(
                "无法启动 Python。请确认已安装 Python，并且 python 命令可用。错误: {}",
                e
            ));
        }
    };

    if output.status.success() {
        return Ok(());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let detail = stdout.trim();
    let extra = stderr.trim();
    let install_hint =
        "请先安装依赖: python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg proglog";

    if detail.is_empty() {
        Err(format!("Python 环境检查失败。{}\n{}", install_hint, extra))
    } else if extra.is_empty() {
        Err(format!("Python 环境检查失败: {}\n{}", detail, install_hint))
    } else {
        Err(format!(
            "Python 环境检查失败: {}\n{}\n{}",
            detail, extra, install_hint
        ))
    }
}

fn find_v5_engine_script(app: &AppHandle) -> Result<PathBuf, String> {
    find_script(
        app,
        "video_engine_v5.py",
        "无法找到 V5 引擎脚本 video_engine_v5.py。请确认它在项目根目录，或已作为 Tauri resource 打包。",
    )
}

fn find_generator_script(app: &AppHandle) -> Result<PathBuf, String> {
    find_script(
        app,
        "make_bilibili_video_v3.py",
        "无法找到脚本 make_bilibili_video_v3.py。请确认它在项目根目录，或已作为 Tauri resource 打包。",
    )
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

pub fn run() {
    tauri::Builder::default()
        .manage(JobManager::default())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            generate_video,
            cancel_video,
            open_in_explorer,
            scan_v5,
            plan_v5,
            save_blueprint_v5,
            compile_v5,
            preview_title_v5,
            render_v5
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
