"""
Function/config_loader.py
- 실행 위치 기준 Config/google_sheet_config.json 로드
- 필수 키 검증
- exe 실행 시에도 Config 폴더를 외부 동봉하여 운영하는 방식 전제
"""

import json
from pathlib import Path
from typing import Any
from typing import Dict


def load_config(base_dir: Path) -> Dict[str, Any]:
    cfg_path = base_dir / "Config" / "google_sheet_config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config 파일이 없습니다: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 필수 키 검증
    required = ("sheet_id", "auth_dir", "log_dir", "downloads_dir", "headers", "sheet_name_format")
    for k in required:
        if k not in cfg:
            raise ValueError(f"Config 누락 키: {k}")

    return cfg