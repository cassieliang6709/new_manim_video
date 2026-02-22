"""
测试 Google Drive 上传：用 credentials.json + 指定文件夹 ID 上传一个本地 mp4。
用法（在项目根目录）:
    python script/test_drive_upload.py
    python script/test_drive_upload.py /path/to/video.mp4
"""
from pathlib import Path
import sys

# 项目根
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uploader import DriveUploader, DriveUploaderOAuth

FOLDER_ID = "1Jc5ARFYeGSspHkd6ED9psYNX_hnl1lbt"
TOKEN_JSON = ROOT / "token.json"
CREDENTIALS = str(ROOT / "credentials.json")

# 默认用 runs.json 里最近一次成功的视频路径
def _get_default_video() -> Path | None:
    import json
    runs_file = ROOT / "manim_output" / "runs.json"
    if not runs_file.exists():
        return None
    try:
        with open(runs_file, encoding="utf-8") as f:
            runs = json.load(f)
        for r in runs:
            if r.get("status") == "success" and r.get("video_path"):
                p = Path(r["video_path"])
                if p.exists():
                    return p
    except Exception:
        pass
    return None


def main() -> None:
    if len(sys.argv) > 1:
        video_path = Path(sys.argv[1])
    else:
        video_path = _get_default_video()
    if not video_path or not video_path.exists():
        print("未找到可上传的视频。用法: python script/test_drive_upload.py [path/to/video.mp4]")
        if not (ROOT / "manim_output" / "runs.json").exists():
            print("或先在前端成功生成一次视频后再运行本脚本。")
        return
    print(f"上传: {video_path}")
    print(f"文件夹 ID: {FOLDER_ID}")
    if TOKEN_JSON.exists():
        print("使用 OAuth (token.json)")
        uploader = DriveUploaderOAuth(str(TOKEN_JSON), FOLDER_ID)
    else:
        print("使用服务账号 (credentials.json)")
        uploader = DriveUploader(credentials_path=CREDENTIALS, folder_id=FOLDER_ID)
    link = uploader.upload_video(str(video_path), video_path.name)
    if link:
        print("成功:", link)
    else:
        print("上传失败。个人 Gmail 请先运行: python script/authorize_drive.py")


if __name__ == "__main__":
    main()
