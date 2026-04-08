from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def export_video(file_path: str, fmt: str = "mp4") -> dict[str, str | bool]:
    source = Path(file_path)
    if not source.exists():
        return {"success": False, "error": f"File not found: {file_path}"}
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return {"success": False, "error": "ffmpeg not found in PATH"}
    target = source.with_suffix(f".{fmt}")
    cmd = [ffmpeg, "-y", "-i", str(source)]
    if fmt == "gif":
        cmd.extend(["-vf", "fps=12,scale=960:-1:flags=lanczos"])
    cmd.append(str(target))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {"success": False, "error": result.stderr[-500:] or "ffmpeg export failed"}
    return {"success": True, "file_path": str(target)}
