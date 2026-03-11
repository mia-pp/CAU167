"""
ui_log_helper.py
- UI 로그창에 표시할 로그를 필터링/정규화하는 헬퍼
- 로그 파일의 원문을 사용자에게 보기 좋은 문구로 변환
"""


def should_display_log_line(line: str) -> bool:
    """
    UI 로그창에 보여줄 핵심 로그만 통과
    """
    include_keywords = [
        "라이센스 확인",
        "downloaded",
        "parsed_rows=",
        "SHEET_CREATED",
        "SHEET_EXISTS",
        "SHEET_CLEARED",
        "SHEET_COMPACTED",
        "SHEET_TRUNCATED",
        "SHEET_WRITE_OK",
        "DONE success_count=",
        "FAIL[",
        "FATAL",
        "WARN[",
        "Google 인증",
        "시트 메타 조회",
    ]

    exclude_keywords = [
        "FutureWarning",
        "google.auth",
        "google.oauth2",
        "google.api_core",
        "INFO:keyword_report_athena:",
        "WARNING:keyword_report_athena:",
        "ERROR:keyword_report_athena:",
        "INFO:root:",
        "Traceback (most recent call last):",
        "  File ",
    ]

    if any(keyword in line for keyword in exclude_keywords):
        return False

    return any(keyword in line for keyword in include_keywords)


def normalize_log_line(line: str) -> str:
    """
    UI용으로 로그 문구를 조금 정리
    """
    cleaned = line.strip()

    if "���̼��� Ȯ��" in cleaned:
        return "라이센스 확인"

    if "downloaded" in cleaned and "OK[DATE=" in cleaned:
        date_text = extract_date(cleaned)
        if date_text:
            return f"{date_text} CSV 다운로드 완료"
        return cleaned

    if "parsed_rows=" in cleaned and "OK[DATE=" in cleaned:
        date_text = extract_date(cleaned)
        parsed_rows = extract_value_after_keyword(cleaned, "parsed_rows=")
        if date_text and parsed_rows:
            return f"{date_text} CSV 파싱 완료 ({parsed_rows}건)"
        return cleaned

    if "SHEET_CREATED" in cleaned:
        sheet_name = extract_value_in_brackets(cleaned, "NAME")
        if sheet_name:
            return f"{sheet_name} 시트 생성 완료"
        return cleaned

    if "SHEET_EXISTS" in cleaned:
        sheet_name = extract_value_in_brackets(cleaned, "NAME")
        if sheet_name:
            return f"{sheet_name} 기존 시트 사용"
        return cleaned

    if "SHEET_CLEARED" in cleaned:
        sheet_name = extract_value_in_brackets(cleaned, "NAME")
        cleared_rows = extract_value_after_keyword(cleaned, "cleared_rows=")
        if sheet_name and cleared_rows:
            return f"{sheet_name} 값 비움 {cleared_rows}행"
        return cleaned

    if "SHEET_COMPACTED" in cleaned:
        sheet_name = extract_value_in_brackets(cleaned, "NAME")
        compacted_rows = extract_value_after_keyword(cleaned, "removed_blank_rows=")
        if sheet_name and compacted_rows:
            return f"{sheet_name} 빈행 정리 {compacted_rows}행"
        return cleaned

    if "SHEET_TRUNCATED" in cleaned:
        sheet_name = extract_value_in_brackets(cleaned, "NAME")
        deleted_rows = extract_value_after_keyword(cleaned, "deleted_rows=")
        if sheet_name and deleted_rows:
            return f"{sheet_name} 기존 데이터 삭제 {deleted_rows}행"
        return cleaned

    if "SHEET_WRITE_OK" in cleaned:
        sheet_name = extract_value_in_brackets(cleaned, "NAME")
        written_rows = extract_value_after_keyword(cleaned, "written_rows=")
        if sheet_name and written_rows:
            return f"{sheet_name} 시트 적재 완료 {written_rows}행"
        return cleaned

    if "DONE success_count=" in cleaned:
        success_count = extract_value_after_keyword(cleaned, "DONE success_count=")
        fail_count = extract_value_after_keyword(cleaned, "fail_count=")
        if success_count is not None and fail_count is not None:
            return f"완료: 성공 {success_count}건 / 실패 {fail_count}건"
        return cleaned

    if "exceeds grid limits" in cleaned:
        return "시트 쓰기 실패: 시트 row 수 부족 (grid limits 초과)"

    if "고정되지 않은 행을 모두 삭제할 수는 없습니다" in cleaned:
        return "행 삭제 실패: 고정되지 않은 모든 행을 한 번에 삭제할 수 없습니다"

    return cleaned


def extract_date(text: str):
    marker = "OK[DATE="
    if marker not in text:
        return None

    try:
        after = text.split(marker, 1)[1]
        return after.split("]", 1)[0].strip()
    except Exception:
        return None


def extract_value_after_keyword(text: str, keyword: str):
    if keyword not in text:
        return None

    try:
        after = text.split(keyword, 1)[1]
        value = after.split()[0].strip()
        if value.endswith("]"):
            value = value[:-1]
        return value
    except Exception:
        return None


def extract_value_in_brackets(text: str, key: str):
    marker = f"{key}="
    if marker not in text:
        return None

    try:
        after = text.split(marker, 1)[1]
        return after.split("]", 1)[0].strip()
    except Exception:
        return None