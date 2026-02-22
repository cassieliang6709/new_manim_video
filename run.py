"""
run.py  —  快速试跑入口

用法:
    # 最简单（不上传 Drive）
    python run.py "画一个蓝色圆从屏幕左边滚到右边"

    # 带 Drive 上传
    python run.py "画一个蓝色圆从屏幕左边滚到右边" --folder-id YOUR_FOLDER_ID

环境变量:
    GOOGLE_API_KEY   Gemini API key (必须)

前置条件:
    - export GOOGLE_API_KEY=your_key_here  (必须)
    - 二选一:
      1) --local: 本机已安装 manim (pip install manim)，无需 Docker
      2) 不用 --local: Docker Desktop 运行 + docker pull manimcommunity/manim:latest
"""

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

from auditor import SecurityAuditor
from executor import LocalExecutor, SandboxExecutor
from generator import SceneComplexity, SceneDescription
from orchestrator import PipelineStatus, WorkflowOrchestrator
from uploader import DriveUploader


def main() -> None:
    parser = argparse.ArgumentParser(description="Manim 自动生成流水线")
    parser.add_argument("prompt", help="场景描述，例如：'画一个红色正方形旋转一圈'")
    parser.add_argument("--folder-id", default="", help="Google Drive 文件夹 ID（可选）")
    parser.add_argument("--output-dir", default="/tmp/manim_output", help="本地输出目录")
    parser.add_argument("--max-retries", type=int, default=3, help="最多重试次数")
    parser.add_argument("--local", action="store_true", help="用本机 manim 执行，不依赖 Docker")
    args = parser.parse_args()

    # ── 组装各模块 ────────────────────────────────────────────────────
    auditors = [SecurityAuditor()]
    executor = LocalExecutor() if args.local else SandboxExecutor()
    drive_uploader = (
        DriveUploader(credentials_path="credentials.json", folder_id=args.folder_id)
        if args.folder_id
        else None
    )

    orchestrator = WorkflowOrchestrator(
        auditors=auditors,
        executor=executor,
        working_dir=Path(args.output_dir),
        max_retries=args.max_retries,
        drive_uploader=drive_uploader,
    )

    # ── 构造场景描述 ──────────────────────────────────────────────────
    description = SceneDescription(
        title="GeneratedScene",
        narrative=args.prompt,
        complexity=SceneComplexity.MODERATE,
    )

    # ── 运行 ──────────────────────────────────────────────────────────
    print(f"\n🎬  开始生成：{args.prompt}\n")
    result = orchestrator.run(description)

    # ── 输出结果 ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if result.status == PipelineStatus.SUCCESS:
        print("✅  成功！")
        print(f"   视频路径: {result.output_files[0] if result.output_files else '(未找到)'}")
        if result.drive_link:
            print(f"   Drive 链接: {result.drive_link}")
    elif result.status == PipelineStatus.MAX_RETRIES_EXCEEDED:
        print(f"❌  失败：已重试 {result.total_attempts} 次，仍无法生成可运行的代码。")
        print("   建议：换一个更简单的描述，或增加 --max-retries。")
    else:
        print(f"❌  失败：状态 = {result.status.value}")

    print(f"   总共尝试: {result.total_attempts} 次")
    print("=" * 60 + "\n")

    sys.exit(0 if result.status == PipelineStatus.SUCCESS else 1)


if __name__ == "__main__":
    main()
