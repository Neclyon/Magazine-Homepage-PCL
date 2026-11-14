"""构建 PCL2 杂志主页

调用 HomepageBuilder 构建工程，并写入 output/Custom.xaml 与版本号 ini。
"""
import datetime
import hashlib
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUTPUT = REPO / "output" / "Custom.xaml"
INI = REPO / "output" / "Custom.xaml.ini"


def make_version() -> tuple[str, str]:
    """返回 (日期, 时间戳哈希)"""
    date = datetime.datetime.now().strftime("%y%m%d")
    digest = hashlib.md5(struct.pack("<f", time.time())).hexdigest()
    return date, digest


def main() -> int:
    date, digest = make_version()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["MAGAZINE_VERSION_ID"] = f"{date}:{digest[:7]}"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "homepagebuilder.main",
            "build",
            "--project",
            str(ROOT / "Project.yml"),
            "--output-path",
            str(OUTPUT),
        ],
        cwd=ROOT,
        env=env,
    )
    if result.returncode != 0:
        return result.returncode

    INI.write_text(f"{date}:{digest}", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
