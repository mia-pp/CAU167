"""
Function/csv_util.py
- keyword_report_athena.csv 파싱 전용
- CSV 1행은 헤더, 데이터는 2행부터
- CSV의 A열(숫자)은 버리고, 구글시트 A열에는 report_date(YYYY-MM-DD)를 넣는다
- CSV의 D열(name)은 구글시트에 적재하지 않는다
- 인코딩 자동 fallback: utf-8-sig → utf-8 → euc-kr
- 숫자 컬럼(key, count)은 int로 변환하여 반환
  (str 그대로 전달 시 Google Sheets가 ' 접두사를 붙여 문자열로 저장되는 문제 방지)
- 출력 row 형식:
  [report_date, collection, key(int), target, value, tag, count(int)]
"""

import csv
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple


# ==============================
# Constants
# ==============================
ENCODING_CANDIDATES = ["utf-8-sig", "utf-8", "euc-kr"]
EXPECTED_HEADER_TAIL = ["collection", "key", "name", "target", "value", "tag", "count"]
ALLOWED_FIRST_HEADERS = {"", "No"}


def parse_keyword_report_csv(file_path: Path, report_date: str) -> Tuple[List[List[Any]], Dict[str, Any]]:
    # 인코딩 후보를 순서대로 시도
    last_error: Optional[Exception] = None

    for enc in ENCODING_CANDIDATES:
        try:
            return _parse_with_encoding(
                file_path=file_path,
                report_date=report_date,
                encoding=enc,
            )
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error

    raise ValueError("CSV parse failed with unknown error")


def _parse_with_encoding(
    file_path: Path,
    report_date: str,
    encoding: str,
) -> Tuple[List[List[Any]], Dict[str, Any]]:
    rows: list[list[Any]] = []
    skipped_invalid_rows = 0
    warnings = []

    with file_path.open("r", encoding=encoding, newline="") as f:
        reader = csv.reader(f)

        # 첫 행은 헤더
        header = next(reader, None)
        if not header:
            raise ValueError("empty csv header")

        # BOM 제거 및 공백 정리
        normalized_header = [str(col).replace("\ufeff", "").strip() for col in header]

        # 헤더가 예상과 다르면 경고만 남기고 계속 진행
        if not _is_expected_header(normalized_header):
            warnings.append(f"unexpected_header={normalized_header}")

        for r in reader:
            if not r:
                continue

            # 최소 8개 컬럼이 없으면 비정상 행으로 건너뜀
            if len(r) < 8:
                skipped_invalid_rows += 1
                continue

            # CSV A열(No) 제거
            # CSV D열(name) 제거
            # 구글시트 A열에는 report_date 삽입
            # C열(key), H열(count)는 숫자 컬럼 → int 변환
            # (str 그대로 전달 시 Google Sheets가 ' 접두사를 붙여 문자열로 저장)
            out = [
                report_date,
                r[1],
                _to_int(r[2]),
                r[4],
                r[5],
                r[6],
                _to_int(r[7]),
            ]
            rows.append(out)

    parse_info = {
        "encoding": encoding,
        "skipped_invalid_rows": skipped_invalid_rows,
        "warnings": warnings,
    }
    return rows, parse_info


def _to_int(value: str) -> Any:
    # 숫자 문자열을 int로 변환
    # 변환 불가한 값은 원본 문자열 그대로 반환
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return value


def _is_expected_header(normalized_header: List[str]) -> bool:
    """
    첫 번째 컬럼은 '' 또는 'No'를 허용하고,
    뒤 7개 컬럼만 정확히 맞으면 정상 헤더로 본다.
    """
    if len(normalized_header) < 8:
        return False

    first_header = normalized_header[0]
    tail_headers = normalized_header[1:8]

    if first_header not in ALLOWED_FIRST_HEADERS:
        return False

    return tail_headers == EXPECTED_HEADER_TAIL