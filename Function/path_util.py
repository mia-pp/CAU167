"""
path_util.py
- 실행 위치 기준 base_dir 계산
- 일반 python 실행 시에는 프로젝트 루트
- macOS .app 실행 시에는 .app 바깥 폴더를 base_dir로 사용
"""

import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()

        # macOS .app 실행 파일:
        # /.../CAU167.app/Contents/MacOS/CAU167
        if sys.platform == "darwin" and len(exe_path.parents) >= 4 and exe_path.parents[2].suffix == ".app":
            return exe_path.parents[3]

        return exe_path.parent

    return Path(__file__).resolve().parents[1]