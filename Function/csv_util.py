"""
Function/csv_util.py
- keyword_report_athena.csv 파싱 전용
- CSV 1행은 헤더, 데이터는 2행부터
- CSV의 A열(숫자)은 버리고, 구글시트 A열에는 report_date(YYYY-MM-DD)를 넣는다
- CSV의 D열(name)은 구글시트에 적재하지 않는다
- 인코딩 자동 fallback: utf-8-sig → utf-8 → euc-kr
- 출력 row 형식:
  [report_date, collection, key, target, value, tag, count]
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

        header = next(reader, None)
        if not header:
            raise ValueError("empty csv header")

        normalized_header = [str(col).replace("\ufeff", "").strip() for col in header]

        if not _is_expected_header(normalized_header):
            warnings.append(f"unexpected_header={normalized_header}")

        for r in reader:
            if not r:
                continue

            if len(r) < 8:
                skipped_invalid_rows += 1
                continue

            out = [
                report_date,
                r[1],
                r[2],
                r[4],
                r[5],
                r[6],
                r[7],
            ]
            rows.append(out)

    parse_info = {
        "encoding": encoding,
        "skipped_invalid_rows": skipped_invalid_rows,
        "warnings": warnings,
    }
    return rows, parse_info


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