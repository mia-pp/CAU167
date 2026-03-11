"""
Function/path_util.py
- 실행 위치 기준 프로젝트 베이스 디렉토리 반환
- PyInstaller(frozen) 환경: 실행 파일 위치 기준
- 개발 환경: 프로젝트 루트 기준
"""

import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]