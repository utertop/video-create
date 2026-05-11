use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct GenerateVideoPayload {
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
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GenerateVideoResult {
    ok: bool,
    message: String,
    command_preview: String,
    output_path: Option<String>,
}

#[tauri::command]
async fn generate_video(app: AppHandle, payload: GenerateVideoPayload) -> GenerateVideoResult {
    match tauri::async_runtime::spawn_blocking(move || generate_video_blocking(app, payload)).await {
        Ok(result) => result,
        Err(e) => GenerateVideoResult {
            ok: false,
            message: format!("后台生成任务异常结束: {}", e),
            command_preview: String::new(),
            output_path: None,
        },
    }
}

fn generate_video_blocking(app: AppHandle, payload: GenerateVideoPayload) -> GenerateVideoResult {
    let script_path = match find_generator_script(&app) {
        Ok(path) => path,
        Err(message) => {
            return GenerateVideoResult {
                ok: false,
                command_preview: build_command_preview(&payload, None, None),
                message,
                output_path: None,
            };
        }
    };
    let input = payload
        .input_paths
        .first()
        .cloned()
        .unwrap_or_else(|| ".".to_string());
    if payload.output_dir.is_empty() {
        return GenerateVideoResult {
            ok: false,
            command_preview: build_command_preview(&payload, Some(&script_path), None),
            message: "请选择输出目录。".to_string(),
            output_path: None,
        };
    }

    let (output_dir, output_file) = build_output_paths(&payload);
    let command_preview = build_command_preview(&payload, Some(&script_path), Some(&output_dir));

    let mut cmd = std::process::Command::new("python");
    cmd.arg(&script_path);
    if let Some(script_dir) = script_path.parent() {
        cmd.current_dir(script_dir);
    }
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }

    cmd.arg("--input_folder").arg(&input);
    cmd.arg("--output_dir").arg(&output_dir);

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

    let quality = match payload.quality.as_str() {
        "draft" => "normal",
        "standard" => "high",
        "high" => "ultra",
        other => other,
    };
    cmd.arg("--quality").arg(quality);

    cmd.arg("--engine").arg(&payload.render_engine);
    cmd.arg("--ratio").arg(&payload.aspect_ratio);

    if payload.cover {
        cmd.arg("--cover");
    }

    if !payload.output_name.is_empty() {
        cmd.arg("--output_name").arg(&payload.output_name);
    }

    match cmd.spawn() {
        Ok(mut child) => {
            let stdout = child.stdout.take().unwrap();
            let app_clone = app.clone();
            std::thread::spawn(move || {
                let reader = BufReader::new(stdout);
                for line in reader.lines() {
                    if let Ok(l) = line {
                        app_clone.emit("video-progress", l).ok();
                    }
                }
            });

            let stderr = child.stderr.take().unwrap();
            let app_clone_err = app.clone();
            std::thread::spawn(move || {
                let reader = BufReader::new(stderr);
                for line in reader.lines() {
                    if let Ok(l) = line {
                        app_clone_err.emit("video-progress", l).ok();
                    }
                }
            });

            let status = child.wait().unwrap_or_else(|e| panic!("Failed to wait on child: {}", e));

            if status.success() && output_file.is_file() {
                GenerateVideoResult {
                    ok: true,
                    message: format!("视频生成成功：{}", output_file.display()),
                    command_preview,
                    output_path: Some(output_file.display().to_string()),
                }
            } else if status.success() {
                GenerateVideoResult {
                    ok: false,
                    message: format!(
                        "脚本已结束，但没有找到总视频文件：{}",
                        output_file.display()
                    ),
                    command_preview,
                    output_path: Some(output_file.display().to_string()),
                }
            } else {
                GenerateVideoResult {
                    ok: false,
                    message: format!("执行失败，退出状态: {}", status),
                    command_preview,
                    output_path: None,
                }
            }
        }
        Err(e) => GenerateVideoResult {
            ok: false,
            message: format!("无法启动 Python 进程: {}", e),
            command_preview,
            output_path: None,
        },
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
    let quality = match payload.quality.as_str() {
        "draft" => "normal",
        "standard" => "high",
        "high" => "ultra",
        other => other,
    };

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

    args.extend([
        "--watermark".to_string(),
        quote(&payload.watermark),
        "--quality".to_string(),
        quality.to_string(),
        "--engine".to_string(),
        payload.render_engine.clone(),
        "--ratio".to_string(),
        payload.aspect_ratio.clone(),
    ]);

    if payload.cover {
        args.push("--cover".to_string());
    }

    args.extend(["--output_name".to_string(), quote(&payload.output_name)]);
    args.join(" ")
}

fn quote(value: &str) -> String {
    format!("\"{}\"", value.replace('"', "\\\""))
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

#[tauri::command]
fn open_in_explorer(path: String) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        let _ = std::process::Command::new("explorer")
            .arg(format!("/select,{}", path))
            .creation_flags(0x08000000)
            .spawn();
    }
}

fn find_generator_script(app: &AppHandle) -> Result<PathBuf, String> {
    let file_name = "make_bilibili_video_v3.py";
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
        .ok_or_else(|| {
            format!(
                "无法找到脚本 {}。请确认它在项目根目录，或已作为 Tauri resource 打包。",
                file_name
            )
        })
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![generate_video, open_in_explorer])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
