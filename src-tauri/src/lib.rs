use serde::{Deserialize, Serialize};

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
fn generate_video(payload: GenerateVideoPayload) -> GenerateVideoResult {
    let command_preview = build_command_preview(&payload);

    let mut cmd = std::process::Command::new("python");
    cmd.arg("make_bilibili_video_v3.py");

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

    match cmd.output() {
        Ok(output) => {
            if output.status.success() {
                GenerateVideoResult {
                    ok: true,
                    message: "视频生成成功！请在输出目录查看。".to_string(),
                    command_preview,
                    output_path: None,
                }
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr);
                let stdout = String::from_utf8_lossy(&output.stdout);
                // 截取最后一点日志防止过长
                let err_msg = if stderr.is_empty() { &stdout } else { &stderr };
                let short_err: String = err_msg.chars().rev().take(500).collect::<String>().chars().rev().collect();
                
                GenerateVideoResult {
                    ok: false,
                    message: format!("执行失败:\n{}", short_err),
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

fn build_command_preview(payload: &GenerateVideoPayload) -> String {
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
        "make_bilibili_video_v3.py".to_string(),
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

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![generate_video])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
