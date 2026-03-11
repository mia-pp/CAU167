"""
Service/orchestrator.py
- 전체 실행 흐름(다운로드 → CSV 파싱 → 월별 시트 생성/write)을 관리
- 기간(start_date~end_date) 동안 날짜별로 처리하고, 결과는 월별 시트(YYYY.MM)에 누적 반영
- 재실행 시 각 월별 실행 구간에 해당하는 데이터만 삭제 후 다시 적재
"""

from datetime import date
from pathlib import Path
from typing import Callable
from typing import Optional

from Common.log import log_fail
from Common.log import log_ok
from Function.csv_util import parse_keyword_report_csv
from Function.date_util import daterange
from Service.downloader import download_with_retry
from Service.google_oauth import get_credentials
from Service.sheet_writer import build_sheets_service
from Service.sheet_writer import ensure_sheet
from Service.sheet_writer import fetch_sheet_metadata
from Service.sheet_writer import refresh_sheet_metadata
from Service.sheet_writer import sheet_exists
from Service.sheet_writer import write_rows
from Service.sheet_writer import clear_rows_in_date_range
from Service.sheet_writer import compact_sheet_rows


# ==============================
# Constants
# ==============================
DOWNLOAD_URL_TEMPLATE = "http://intwg.kakaocdn.net/clean_image/sapiens/report/{date}_keyword_report_athena.csv"

MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 2

CODE_CSV_PARSE_ERR = "CSV_PARSE_ERR"
CODE_GSHEET_WRITE_ERR = "GSHEET_WRITE_ERR"
CODE_GSHEET_AUTH_ERR = "GSHEET_AUTH_ERR"
CODE_GSHEET_ACCESS_ERR = "GSHEET_ACCESS_ERR"


def run(
    *,
    base_dir: Path,
    config: dict,
    logger,
    start_date: date,
    end_date: date,
    progress_callback: Optional[Callable[[int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    sheet_id = config["sheet_id"]
    auth_dir = config["auth_dir"]
    downloads_dir_name = config["downloads_dir"]
    headers = config["headers"]
    sheet_name_format = config["sheet_name_format"]

    downloads_dir = base_dir / downloads_dir_name
    downloads_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0

    total_days = (end_date - start_date).days + 1
    processed_days = 0

    # UI/외부에서 콜백이 전달된 경우에만 상태 반영
    def emit_progress(value: int) -> None:
        if progress_callback:
            progress_callback(value)

    def emit_status(message: str) -> None:
        if status_callback:
            status_callback(message)

    def emit_log(message: str) -> None:
        if log_callback:
            log_callback(message)

    try:
        # Google Sheets 인증 및 서비스 생성
        emit_status("Google 인증")
        emit_log("Google 인증")
        emit_progress(20)

        creds = get_credentials(base_dir, auth_dir)
        service = build_sheets_service(creds)
    except Exception as e:
        log_fail(
            logger=logger,
            report_date=start_date.strftime("%Y-%m-%d"),
            code=CODE_GSHEET_AUTH_ERR,
            try_no=1,
            message=str(e),
            extra="Google OAuth 인증 실패",
        )
        raise

    try:
        # 대상 스프레드시트 메타 정보 조회
        emit_status("시트 메타 조회")
        emit_log("시트 메타 조회")
        emit_progress(25)

        metadata = fetch_sheet_metadata(service, sheet_id)
    except Exception as e:
        log_fail(
            logger=logger,
            report_date=start_date.strftime("%Y-%m-%d"),
            code=CODE_GSHEET_ACCESS_ERR,
            try_no=1,
            message=str(e),
            extra=f"sheet_id={sheet_id}",
        )
        raise

    month_rows_map = {}
    month_range_map = {}

    # ------------------------------
    # 1) 다운로드 + 파싱 단계 (25 ~ 70)
    # ------------------------------
    for d in daterange(start_date, end_date):
        sheet_title = sheet_name_format.format(yyyy=f"{d.year:04d}", mm=f"{d.month:02d}")
        report_date = d.strftime("%Y-%m-%d")

        emit_status(f"{report_date} 다운로드/파싱")
        emit_log(f"{report_date} 다운로드 시작")

        # 월별 시트 단위로 적재 데이터를 모으고,
        # 해당 월에서 이번 실행 구간의 시작일/종료일도 함께 기록
        if sheet_title not in month_rows_map:
            month_rows_map[sheet_title] = []
            month_range_map[sheet_title] = {
                "start_date": report_date,
                "end_date": report_date,
            }
        else:
            month_range_map[sheet_title]["end_date"] = report_date

        url = DOWNLOAD_URL_TEMPLATE.format(date=report_date)
        save_path = downloads_dir / f"{report_date}_keyword_report_athena.csv"

        ok, actual_save_path = download_with_retry(
            logger=logger,
            url=url,
            report_date=report_date,
            save_path=save_path,
            max_retries=MAX_RETRIES,
            sleep_seconds=RETRY_SLEEP_SECONDS,
        )

        if not ok or actual_save_path is None:
            fail_count += 1
            emit_log(f"{report_date} 다운로드 실패")
            processed_days += 1
            emit_progress(25 + int((processed_days / total_days) * 45))
            continue

        try:
            # 다운로드한 CSV를 파싱해서 월별 적재 목록에 누적
            rows, parse_info = parse_keyword_report_csv(actual_save_path, report_date)
            month_rows_map[sheet_title].extend(rows)
            success_count += 1

            log_ok(
                logger,
                report_date,
                f"parsed_rows={len(rows)} encoding={parse_info['encoding']}",
            )
            emit_log(f"{report_date} parsed_rows={len(rows)}")

            # 건너뛴 비정상 행이나 헤더 경고는 warning 로그로 남김
            if parse_info["skipped_invalid_rows"] > 0:
                warning_msg = f"{report_date} skipped_invalid_rows={parse_info['skipped_invalid_rows']}"
                logger.warning(f"WARN[DATE={report_date}] skipped_invalid_rows={parse_info['skipped_invalid_rows']}")
                emit_log(warning_msg)

            for warning_msg in parse_info["warnings"]:
                logger.warning(f"WARN[DATE={report_date}] {warning_msg}")
                emit_log(f"{report_date} {warning_msg}")

        except Exception as e:
            fail_count += 1
            log_fail(
                logger=logger,
                report_date=report_date,
                code=CODE_CSV_PARSE_ERR,
                try_no=1,
                message=str(e),
                extra=str(actual_save_path),
            )
            emit_log(f"{report_date} 파싱 실패: {e}")

        processed_days += 1
        emit_progress(25 + int((processed_days / total_days) * 45))

    # ------------------------------
    # 2) 월별 시트 반영 단계 (70 ~ 95)
    # ------------------------------
    emit_status("월별 시트 반영 준비")
    emit_log("월별 시트 반영 준비")
    emit_progress(70)

    month_titles = sorted(month_rows_map.keys())
    month_count = len(month_titles)

    if month_count == 0:
        emit_status("적재 대상 없음")
        emit_log("적재 대상 월 데이터 없음")
        emit_progress(100)

        return {
            "success_count": success_count,
            "fail_count": fail_count,
        }

    for index, sheet_title in enumerate(month_titles, start=1):
        rows = month_rows_map[sheet_title]
        range_info = month_range_map[sheet_title]
        month_start_report_date = range_info["start_date"]
        month_end_report_date = range_info["end_date"]

        emit_status(f"{sheet_title} 시트 반영")
        emit_log(f"{sheet_title} 시트 반영 시작")

        exists = sheet_exists(metadata, sheet_title)

        if not exists:
            # 월 시트가 없으면 새로 생성
            ensure_sheet(service, sheet_id, metadata, sheet_title, headers)
            refresh_sheet_metadata(service, sheet_id, metadata)
            logger.info(f"SHEET_CREATED[NAME={sheet_title}] 월 시트 생성 완료")
            emit_log(f"{sheet_title} 시트 생성 완료")
        else:
            # 재실행 시에는 이번 실행 구간 날짜만 먼저 비움
            logger.info(f"SHEET_EXISTS[NAME={sheet_title}] 기존 월 시트 사용")
            emit_log(f"{sheet_title} 기존 시트 사용")

            cleared_count = clear_rows_in_date_range(
                service=service,
                spreadsheet_id=sheet_id,
                sheet_title=sheet_title,
                start_report_date=month_start_report_date,
                end_report_date=month_end_report_date,
            )

            logger.info(
                f"SHEET_CLEARED[NAME={sheet_title}][START_DATE={month_start_report_date}][END_DATE={month_end_report_date}] "
                f"cleared_rows={cleared_count}"
            )
            emit_log(f"{sheet_title} 값 비움 {cleared_count}행")

            # 값만 비운 뒤 생긴 빈 행은 정리
            compacted_count = compact_sheet_rows(
                service=service,
                spreadsheet_id=sheet_id,
                metadata=metadata,
                sheet_title=sheet_title,
            )

            logger.info(
                f"SHEET_COMPACTED[NAME={sheet_title}] removed_blank_rows={compacted_count}"
            )
            emit_log(f"{sheet_title} 빈행 정리 {compacted_count}행")

        if not rows:
            logger.info(f"SHEET_WRITE_SKIPPED[NAME={sheet_title}] write 대상 데이터 없음")
            emit_log(f"{sheet_title} write 대상 데이터 없음")
            emit_progress(70 + int((index / month_count) * 25))
            continue

        try:
            # 월별 누적 데이터 시트에 write
            write_rows(service, sheet_id, metadata, sheet_title, rows)
            logger.info(
                f"SHEET_WRITE_OK[NAME={sheet_title}][START_DATE={month_start_report_date}][END_DATE={month_end_report_date}] "
                f"written_rows={len(rows)}"
            )
            emit_log(f"{sheet_title} written_rows={len(rows)}")
        except Exception as e:
            fail_count += 1
            log_fail(
                logger=logger,
                report_date=month_start_report_date,
                code=CODE_GSHEET_WRITE_ERR,
                try_no=1,
                message=str(e),
                extra=f"SHEET={sheet_title}",
            )
            emit_log(f"{sheet_title} write 실패: {e}")

        emit_progress(70 + int((index / month_count) * 25))

    emit_status("완료")
    emit_log("전체 작업 완료")
    emit_progress(100)

    return {
        "success_count": success_count,
        "fail_count": fail_count,
    }