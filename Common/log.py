"""
log.py
- CAU167 공용 로거 생성
- 파일/콘솔 로그를 동시에 남김
- 중복 핸들러와 상위 로거 전파를 막아 UI/콘솔 중복 로그를 줄임
"""

import logging
from pathlib import Path


# ==============================
# Constants
# ==============================
LOGGER_NAME = "keyword_report_athena"
LOG_FILE_PREFIX = "log_"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def build_logger(log_dir: Path) -> logging.Logger:
    """
    log_dir 하위에 날짜별 로그 파일 생성
    예: log_20260311.log
    """
    # 로그 폴더가 없으면 생성
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)

    # 기존 핸들러 제거 (중복 로그 방지)
    if logger.handlers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    # 상위 로거로 전파되지 않도록 설정
    logger.propagate = False

    log_file_path = log_dir / f"{LOG_FILE_PREFIX}{_today_yyyymmdd()}.log"
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # 파일 로그 저장용 핸들러
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # 콘솔 출력용 핸들러
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


def log_ok(logger: logging.Logger, report_date: str, message: str) -> None:
    # 정상 처리 로그 기록
    logger.info(f"OK[DATE={report_date}] {message}")


def log_fail(
    logger: logging.Logger,
    report_date: str,
    code: str,
    try_no: int,
    message: str,
    extra: str = "",
) -> None:
    # 실패 로그 기록
    if extra:
        logger.error(f"FAIL[DATE={report_date}][CODE={code}][TRY={try_no}] {message} | {extra}")
    else:
        logger.error(f"FAIL[DATE={report_date}][CODE={code}][TRY={try_no}] {message}")


def _today_yyyymmdd() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d")