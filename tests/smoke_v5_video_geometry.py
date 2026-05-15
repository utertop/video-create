import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import imageio_ffmpeg

import video_engine_v5 as engine


def make_test_video(path: Path, size: str, sar: str = "1/1") -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.check_call(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s={size}:d=0.5:r=12",
            "-vf",
            f"setsar={sar}",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_video_display_geometry_detection() -> None:
    root = Path("tests/tmp_video_geometry_probe")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    normal = root / "normal.mp4"
    non_square_pixel = root / "sar_16_9.mp4"

    make_test_video(normal, "1280x720")
    make_test_video(non_square_pixel, "720x576", "64/45")

    assert not engine.video_needs_display_normalization(normal)
    assert engine.video_needs_display_normalization(non_square_pixel)


if __name__ == "__main__":
    test_video_display_geometry_detection()
    print("V5 video geometry smoke test passed")
