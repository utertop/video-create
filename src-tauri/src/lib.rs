use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct GenerateVideoPayload {
    input_paths: Vec<String>,
    title: String,
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
fn generate_video(app: AppHandle, payload: GenerateVideoPayload) -> GenerateVideoResult {
    let script_path = match find_generator_script(&app) {
        Ok(path) => path,
        Err(message) => {
            return GenerateVideoResult {
                ok: false,
                command_preview: build_command_preview(&payload, None),
                message,
                output_path: None,
            };
        }
    };
    let command_preview = build_command_preview(&payload, Some(&script_path));

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

    let input = payload
        .input_paths
        .first()
        .cloned()
        .unwrap_or_else(|| ".".to_string());
    
    cmd.arg("--input_folder").arg(&input);

    if payload.recursive {
        cmd.arg("--recursive");
    }

    if payload.chapters_from_dirs {
        cmd.arg("--chapters_from_dirs");
    }

    if !payload.title.is_empty() {
        cmd.arg("--title").arg(&payload.title);
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

            if status.success() {
                GenerateVideoResult {
                    ok: true,
                    message: "视频生成成功！请在输出目录查看。".to_string(),
                    command_preview,
                    output_path: None,
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

fn build_command_preview(payload: &GenerateVideoPayload, script_path: Option<&Path>) -> String {
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

    if payload.recursive {
        args.push("--recursive".to_string());
    }

    if payload.chapters_from_dirs {
        args.push("--chapters_from_dirs".to_string());
    }

    args.extend([
        "--title".to_string(),
        quote(&payload.title),
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
        .invoke_handler(tauri::generate_handler![generate_video])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
