SCHEMA_VERSION = "5.5"
ENGINE_VERSION = "video-create-engine-v5.6.3"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")
ALL_EXTS = IMAGE_EXTS + VIDEO_EXTS + AUDIO_EXTS

IGNORED_DIRS = {
    "__pycache__",
    "node_modules",
    "dist",
    "target",
    "output",
    "outputs",
    ".git",
    ".cache_video_create_v5",
    ".thumbnails",
}
IGNORED_FILES = {"thumbs.db", ".ds_store"}

CACHE_CLEANUP_DEFAULTS_MB = {
    "render_cache": 2048,
    "audio_cache": 768,
    "proxies": 1024,
    "chunks": 4096,
    "scan_proxies": 1024,
    "thumbnails": 256,
}

