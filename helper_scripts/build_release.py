"""Build the same application bundle locally and in GitHub Actions."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from packaging.version import Version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--arch", choices=("x86_64", "arm64"), default="")
    args = parser.parse_args()
    version = str(Version(args.version))
    if Path(args.name).name != args.name or any(c in args.name for c in "/\\:"):
        parser.error("The bundle name must be a filename, not a path")

    root = Path(__file__).resolve().parents[1]
    version_file = root / "pzero" / "_version.py"
    original = version_file.read_bytes()
    env = dict(os.environ, PZERO_BUILD_NAME=args.name, PZERO_BUILD_ARCH=args.arch)
    try:
        version_file.write_text(f"__version__ = {version!r}\n", encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--workpath",
            "build/release",
            "packaging/pzero.spec",
        ]
        if sys.platform == "darwin" and args.arch:
            command = ["arch", f"-{args.arch}", *command]
        subprocess.run(
            command,
            cwd=root,
            env=env,
            check=True,
        )
    finally:
        version_file.write_bytes(original)


if __name__ == "__main__":
    main()
