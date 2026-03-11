"""
Service/downloader.py
- 날짜별 URL 템플릿에 date(YYYY-MM-DD)만 치환해서 CSV 다운로드
- 실패 사유코드 로그 기록 + 재시도(MAX_RETRIES) 수행
- 기존 파일이 잠겨 있거나 삭제 실패하면 대체 파일명으로 저장
- 실제 저장된 파일 경로를 반환하여, 그 파일로 바로 파싱/업로드할 수 있게 처리
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from typing import Tuple

import requests

from Common.log import log_fail
from Common.log import log_ok


# ==============================
# Constants
# ==============================
CODE_HTTP_404 = "HTTP_404"
CODE_HTTP_ERROR = "HTTP_ERROR"
CODE_ZERO_BYTES = "ZERO_BYTES"
CODE_DOWNLOAD_ERR = "DOWNLOAD_ERR"
CODE_FILE_DELETE_ERR = "FILE_DELETE_ERR"
CODE_FILE_LOCKED_FALLBACK = "FILE_LOCKED_FALLBACK"


def download_with_retry(
    *,
    logger,
    url: str,
    report_date: str,
    save_path: Path,
    max_retries: int,
    sleep_seconds: int,
) -> Tuple[bool, Optional[Path]]:
    """
    url: 다운로드 대상 URL
    report_date: 처리 날짜(YYYY-MM-DD) → 로그 키
    save_path: 기본 저장 경로
    max_retries: 최대 재시도 횟수
    sleep_seconds: 재시도 대기 시간(초)

    return:
        (성공 여부, 실제 저장된 파일 경로)
    """
    save_path.parent.mkdir(parents=True, exist_ok=True)

    for try_no in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=30)

            if resp.status_code == 404:
                log_fail(logger, report_date, CODE_HTTP_404, try_no, "file not found", url)
                time.sleep(sleep_seconds)
                continue

            if resp.status_code != 200:
                log_fail(logger, report_date, CODE_HTTP_ERROR, try_no, f"status={resp.status_code}", url)
                time.sleep(sleep_seconds)
                continue

            actual_save_path = _resolve_save_path(
                logger=logger,
                report_date=report_date,
                try_no=try_no,
                save_path=save_path,
            )
            if actual_save_path is None:
                time.sleep(sleep_seconds)
                continue

            actual_save_path.write_bytes(resp.content)

            if actual_save_path.stat().st_size == 0:
                log_fail(
                    logger,
                    report_date,
                    CODE_ZERO_BYTES,
                    try_no,
                    "downloaded file is 0 bytes",
                    str(actual_save_path),
                )
                time.sleep(sleep_seconds)
                continue

            if actual_save_path == save_path:
                log_ok(logger, report_date, f"downloaded {actual_save_path.name}")
            else:
                log_ok(
                    logger,
                    report_date,
                    f"downloaded alt_file={actual_save_path.name} (original_locked={save_path.name})",
                )

            return True, actual_save_path

        except Exception as e:
            log_fail(logger, report_date, CODE_DOWNLOAD_ERR, try_no, str(e), url)
            time.sleep(sleep_seconds)

    return False, None


def _resolve_save_path(logger, report_date: str, try_no: int, save_path: Path) -> Optional[Path]:
    """
    저장 경로 결정
    - 기본 파일이 없으면 그대로 사용
    - 기본 파일이 있으면 삭제 시도
    - 삭제 실패하면 대체 파일명 생성
    """
    if not save_path.exists():
        return save_path

    try:
        save_path.unlink()
        return save_path

    except Exception as e:
        log_fail(
            logger,
            report_date,
            CODE_FILE_DELETE_ERR,
            try_no,
            str(e),
            str(save_path),
        )

        alt_path = _build_alt_save_path(save_path)

        log_fail(
            logger,
            report_date,
            CODE_FILE_LOCKED_FALLBACK,
            try_no,
            "save with alternative filename",
            str(alt_path),
        )

        return alt_path


def _build_alt_save_path(save_path: Path) -> Path:
    """
    기본 파일명 저장이 어려울 때 사용할 대체 파일명 생성
    예:
    2026-03-01_keyword_report_athena.csv
    -> 2026-03-01_keyword_report_athena_20260310_143210.csv
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = save_path.stem
    suffix = save_path.suffix

    alt_name = f"{stem}_{timestamp}{suffix}"
    return save_path.parent / alt_name