"""
sheet_writer.py
- Google Sheets API(v4) 기반 시트 생성/헤더 세팅/데이터 write
- 월별 시트 생성 규칙:
  1) 전달(이전 월) 시트가 있으면:
     - 전달 오른쪽에 새 시트 생성 > 전달의 1행 서식만 복사 > 헤더 입력 > 1행 고정
  2) 전달 시트가 없으면:
     - 마지막 월시트 오른쪽에 새 시트 생성 > 헤더 입력 > 1행 고정
- 재실행 시 실행 구간(start_date ~ end_date)에 해당하는 데이터만 clear
- clear 후 빈행 정리(compact) 수행
  - compact 시 API 읽기로 반환된 str 값 중 숫자 컬럼(key, count)을 int로 재변환 후 write
    (재write 시 ' 접두사 문제 방지)
- 데이터 입력은 values.update 방식으로 처리
- write 후:
  - 기존 데이터 아래 다음 행부터 이어서 입력
  - A열(report_date) 기준 오름차순 정렬
  - 2행부터 데이터 영역 전체 테두리 적용
  - A:G 열 기본 너비 100 설정
  - E열(value) auto resize 후 100~400 사이로 보정
"""

from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from googleapiclient.discovery import build


# ==============================
# Constants
# ==============================
DEFAULT_FREEZE_ROWS = 1

FIRST_DATA_ROW = 2
REPORT_DATE_COLUMN_RANGE = f"A{FIRST_DATA_ROW}:A"

LAST_COLUMN_LETTER = "G"
LAST_COLUMN_INDEX = 7  # A~G (end exclusive)
TOTAL_COLUMNS = 7

DEFAULT_COLUMN_WIDTH = 100
VALUE_COLUMN_INDEX = 4
VALUE_COLUMN_MIN_WIDTH = 100
VALUE_COLUMN_MAX_WIDTH = 400

# 시트 컬럼별 타입 정의 (0-based index)
# A(0): report_date - str
# B(1): collection  - str
# C(2): key         - int ← 숫자
# D(3): target      - str
# E(4): value       - str
# F(5): tag         - str
# G(6): count       - int ← 숫자
_INT_COLUMNS = {2, 6}


def _normalize_row_types(row: List[Any]) -> List[Any]:
    """
    Google Sheets API values().get()은 모든 값을 str로 반환한다.
    compact_sheet_rows 등에서 읽어 다시 write할 때 숫자 컬럼(key, count)을
    int로 변환하지 않으면 ' 접두사가 붙은 문자열로 재적재되는 문제 방지.
    변환 불가한 값은 원본 그대로 유지한다.
    """
    result = []
    for i, val in enumerate(row):
        if i in _INT_COLUMNS:
            try:
                result.append(int(str(val).strip()))
            except (ValueError, TypeError):
                result.append(val)
        else:
            result.append(val)
    return result


def build_sheets_service(creds):
    # Google Sheets API 서비스 객체 생성
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def fetch_sheet_metadata(service, spreadsheet_id: str) -> Dict[str, Any]:
    """
    시트 메타/속성을 한 번에 읽어 캐시용 dict로 반환
    """
    response = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title,index,gridProperties(rowCount)))",
    ).execute()

    sheets = response.get("sheets", [])
    by_title = {}
    by_id = {}

    for sheet in sheets:
        props = sheet.get("properties", {})
        title = props.get("title")
        sheet_id = int(props.get("sheetId"))
        row_count = int(props.get("gridProperties", {}).get("rowCount", 0))
        index = int(props.get("index", 0))

        info = {
            "sheet_id": sheet_id,
            "title": title,
            "index": index,
            "row_count": row_count,
        }
        by_title[title] = info
        by_id[sheet_id] = info

    return {
        "by_title": by_title,
        "by_id": by_id,
    }


def refresh_sheet_metadata(service, spreadsheet_id: str, metadata: Dict[str, Any]) -> None:
    # 시트 생성/변경 후 메타 캐시 갱신
    refreshed = fetch_sheet_metadata(service, spreadsheet_id)
    metadata.clear()
    metadata.update(refreshed)


def sheet_exists(metadata: Dict[str, Any], sheet_title: str) -> bool:
    return sheet_title in metadata["by_title"]


def ensure_sheet(
    service,
    spreadsheet_id: str,
    metadata: Dict[str, Any],
    sheet_title: str,
    headers: list[str],
) -> None:
    """
    시트가 없으면 생성한다.
    """
    if sheet_exists(metadata, sheet_title):
        # 이미 있으면 1행 고정만 보장
        sheet_id = metadata["by_title"][sheet_title]["sheet_id"]
        _freeze_first_row(service, spreadsheet_id, sheet_id)
        return

    prev_title = _get_prev_month_title(sheet_title)
    prev_exists = prev_title is not None and sheet_exists(metadata, prev_title)

    # 전달 시트가 있으면 전달 오른쪽,
    # 없으면 마지막 월시트 오른쪽에 새 시트 생성
    if prev_exists:
        insert_index = metadata["by_title"][prev_title]["index"] + 1
    else:
        last_month_title = _get_last_month_sheet_title(metadata)

        if last_month_title is not None:
            insert_index = metadata["by_title"][last_month_title]["index"] + 1
        else:
            insert_index = len(metadata["by_title"])

    new_sheet_id = _add_sheet(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_title=sheet_title,
        insert_index=insert_index,
    )

    refresh_sheet_metadata(service, spreadsheet_id, metadata)

    # 전달 시트가 있으면 1행 서식만 복사
    if prev_exists:
        prev_sheet_id = metadata["by_title"][prev_title]["sheet_id"]
        _copy_first_row_format(
            service=service,
            spreadsheet_id=spreadsheet_id,
            source_sheet_id=prev_sheet_id,
            destination_sheet_id=new_sheet_id,
        )

    # 헤더 입력
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!A1:{LAST_COLUMN_LETTER}1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()

    # 1행 고정
    _freeze_first_row(service, spreadsheet_id, new_sheet_id)


def write_rows(
    service,
    spreadsheet_id: str,
    metadata: Dict[str, Any],
    sheet_title: str,
    rows: List[List[Any]],
) -> None:
    """
    기존 데이터 아래 다음 행부터 write 후 정렬/서식 처리
    """
    if not rows:
        return

    sheet_id = metadata["by_title"][sheet_title]["sheet_id"]

    # 현재 마지막 데이터 행 다음부터 이어서 입력
    last_data_row = _get_last_data_row(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_title=sheet_title,
    )
    start_row = last_data_row + 1
    if start_row < FIRST_DATA_ROW:
        start_row = FIRST_DATA_ROW

    end_row = start_row + len(rows) - 1
    target_range = f"{sheet_title}!A{start_row}:{LAST_COLUMN_LETTER}{end_row}"

    # 필요한 경우 시트 row 수 확장
    _ensure_row_capacity(
        service=service,
        spreadsheet_id=spreadsheet_id,
        metadata=metadata,
        sheet_title=sheet_title,
        required_last_row=end_row,
    )

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=target_range,
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # write 후 정렬/테두리/열 너비 후처리
    _finalize_sheet_layout(
        service=service,
        spreadsheet_id=spreadsheet_id,
        metadata=metadata,
        sheet_title=sheet_title,
        sheet_id=sheet_id,
    )


def clear_rows_in_date_range(
    service,
    spreadsheet_id: str,
    sheet_title: str,
    start_report_date: str,
    end_report_date: str,
) -> int:
    """
    A열(report_date) 기준으로 start_report_date ~ end_report_date 범위에 해당하는 행의 값만 비운다.
    행 자체는 삭제하지 않는다.

    return:
        clear 처리한 행 수
    """
    values_resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!{REPORT_DATE_COLUMN_RANGE}",
    ).execute()

    values = values_resp.get("values", [])
    if not values:
        return 0

    matching_rows = []

    # A열 날짜를 기준으로 clear 대상 행 찾기
    for index, row in enumerate(values, start=FIRST_DATA_ROW):
        if not row or not row[0]:
            continue

        report_date = row[0]
        if start_report_date <= report_date <= end_report_date:
            matching_rows.append(index)

    if not matching_rows:
        return 0

    # 연속 행은 묶어서 batchClear 범위 최소화
    row_ranges = _compress_row_ranges(matching_rows)

    clear_ranges = []
    cleared_count = 0

    for start_row, end_row in row_ranges:
        clear_ranges.append(f"{sheet_title}!A{start_row}:{LAST_COLUMN_LETTER}{end_row}")
        cleared_count += end_row - start_row + 1

    service.spreadsheets().values().batchClear(
        spreadsheetId=spreadsheet_id,
        body={"ranges": clear_ranges},
    ).execute()

    return cleared_count


def compact_sheet_rows(
    service,
    spreadsheet_id: str,
    metadata: Dict[str, Any],
    sheet_title: str,
) -> int:
    """
    2행부터 마지막 데이터 영역을 읽어서 완전 빈 행을 제거한 뒤,
    남은 데이터만 2행부터 다시 write한다.
    아래쪽 꼬리 영역은 clear 처리한다.

    처리 단계:
    1) 기존 데이터 전체 읽기
    2) 완전 빈 행 제거
    3) 남은 데이터만 2행부터 다시 쓰기
    4) 줄어든 꼬리 영역 clear
    5) 정렬/테두리/열 너비 재적용

    return:
        제거된 빈 행 수
    """
    all_rows = _read_data_rows(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_title=sheet_title,
    )

    if not all_rows:
        return 0

    original_count = len(all_rows)
    # 빈 행 제거 + 숫자 컬럼 타입 정규화
    # (API 읽기 시 모든 값이 str로 반환되므로 재write 전 int 변환 필요)
    compacted_rows = [
        _normalize_row_types(row)
        for row in all_rows
        if _has_any_value(row)
    ]
    compacted_count = len(compacted_rows)
    removed_blank_count = original_count - compacted_count

    sheet_id = metadata["by_title"][sheet_title]["sheet_id"]

    # 1) 남길 데이터 다시 2행부터 write
    if compacted_rows:
        end_row = FIRST_DATA_ROW + compacted_count - 1

        _ensure_row_capacity(
            service=service,
            spreadsheet_id=spreadsheet_id,
            metadata=metadata,
            sheet_title=sheet_title,
            required_last_row=end_row,
        )

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_title}!A{FIRST_DATA_ROW}:{LAST_COLUMN_LETTER}{end_row}",
            valueInputOption="RAW",
            body={"values": compacted_rows},
        ).execute()

    # 2) 원래 길이보다 줄어든 꼬리 영역 clear
    if compacted_count < original_count:
        clear_start_row = FIRST_DATA_ROW + compacted_count
        clear_end_row = FIRST_DATA_ROW + original_count - 1

        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_title}!A{clear_start_row}:{LAST_COLUMN_LETTER}{clear_end_row}",
            body={},
        ).execute()

    # 3) 정렬/서식 재적용
    _finalize_sheet_layout(
        service=service,
        spreadsheet_id=spreadsheet_id,
        metadata=metadata,
        sheet_title=sheet_title,
        sheet_id=sheet_id,
    )

    return removed_blank_count


def _read_data_rows(
    service,
    spreadsheet_id: str,
    sheet_title: str,
) -> List[List[Any]]:
    """
    2행부터 A:G 데이터를 읽어온다.
    """
    values_resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!A{FIRST_DATA_ROW}:{LAST_COLUMN_LETTER}",
    ).execute()

    return values_resp.get("values", [])


def _has_any_value(row: List[Any]) -> bool:
    """
    행에 하나라도 값이 있으면 True
    """
    for value in row:
        if str(value).strip() != "":
            return True
    return False


def _finalize_sheet_layout(
    service,
    spreadsheet_id: str,
    metadata: Dict[str, Any],
    sheet_title: str,
    sheet_id: int,
) -> None:
    """
    데이터 재배치 이후 공통 후처리
    - report_date 기준 정렬
    - 데이터 영역 테두리 적용
    - A:G 기본 열 너비 적용
    - E열 auto resize + 최소/최대 너비 보정
    """
    last_data_row = _get_last_data_row(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_title=sheet_title,
    )

    # A열(report_date) 기준 오름차순 정렬
    if last_data_row >= FIRST_DATA_ROW:
        _sort_by_report_date(
            service=service,
            spreadsheet_id=spreadsheet_id,
            sheet_id=sheet_id,
            start_row_index=FIRST_DATA_ROW - 1,
            end_row_index=last_data_row,
            start_column_index=0,
            end_column_index=LAST_COLUMN_INDEX,
        )

    last_data_row = _get_last_data_row(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_title=sheet_title,
    )

    # 데이터 영역 전체 테두리 적용
    if last_data_row >= FIRST_DATA_ROW:
        _apply_data_borders(
            service=service,
            spreadsheet_id=spreadsheet_id,
            sheet_id=sheet_id,
            start_row_index=FIRST_DATA_ROW - 1,
            end_row_index=last_data_row,
            start_column_index=0,
            end_column_index=LAST_COLUMN_INDEX,
        )

    # A:G 기본 열 너비 적용
    _set_columns_width(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_id=sheet_id,
        start_column_index=0,
        end_column_index=LAST_COLUMN_INDEX,
        pixel_size=DEFAULT_COLUMN_WIDTH,
    )

    # E열(value)만 auto resize 후 최소/최대 너비 보정
    _auto_resize_columns(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_id=sheet_id,
        start_column_index=VALUE_COLUMN_INDEX,
        end_column_index=VALUE_COLUMN_INDEX + 1,
    )

    current_width = _get_column_width(
        service=service,
        spreadsheet_id=spreadsheet_id,
        sheet_id=sheet_id,
    )

    if current_width < VALUE_COLUMN_MIN_WIDTH:
        _set_column_width(
            service=service,
            spreadsheet_id=spreadsheet_id,
            sheet_id=sheet_id,
            column_index=VALUE_COLUMN_INDEX,
            pixel_size=VALUE_COLUMN_MIN_WIDTH,
        )
    elif current_width > VALUE_COLUMN_MAX_WIDTH:
        _set_column_width(
            service=service,
            spreadsheet_id=spreadsheet_id,
            sheet_id=sheet_id,
            column_index=VALUE_COLUMN_INDEX,
            pixel_size=VALUE_COLUMN_MAX_WIDTH,
        )


def _compress_row_ranges(row_numbers: List[int]) -> List[tuple]:
    # 연속된 행 번호를 start/end 범위로 압축
    if not row_numbers:
        return []

    sorted_rows = sorted(row_numbers)
    ranges = []

    start_row = sorted_rows[0]
    prev_row = sorted_rows[0]

    for row in sorted_rows[1:]:
        if row == prev_row + 1:
            prev_row = row
            continue

        ranges.append((start_row, prev_row))
        start_row = row
        prev_row = row

    ranges.append((start_row, prev_row))
    return ranges


def _get_last_data_row(service, spreadsheet_id: str, sheet_title: str) -> int:
    # A열 기준 마지막 사용 행 번호 반환
    values_resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!A:A",
    ).execute()

    values = values_resp.get("values", [])
    return len(values)


def _ensure_row_capacity(
    service,
    spreadsheet_id: str,
    metadata: Dict[str, Any],
    sheet_title: str,
    required_last_row: int,
) -> None:
    # 필요한 마지막 행이 현재 row 수를 넘으면 시트 row 확장
    current_row_count = metadata["by_title"][sheet_title]["row_count"]

    if required_last_row <= current_row_count:
        return

    sheet_id = metadata["by_title"][sheet_title]["sheet_id"]

    body = {
        "requests": [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "rowCount": required_last_row,
                        },
                    },
                    "fields": "gridProperties.rowCount",
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()

    metadata["by_title"][sheet_title]["row_count"] = required_last_row


def _get_prev_month_title(sheet_title: str) -> Optional[str]:
    # YYYY.MM 기준 전달 시트명 계산
    try:
        yyyy_str, mm_str = sheet_title.split(".")
        yyyy = int(yyyy_str)
        mm = int(mm_str)
    except Exception:
        return None

    if mm == 1:
        return f"{yyyy - 1:04d}.12"

    return f"{yyyy:04d}.{mm - 1:02d}"


def _get_last_month_sheet_title(metadata: Dict[str, Any]) -> Optional[str]:
    # 현재 스프레드시트 안의 마지막 월시트명 조회
    month_titles = []

    for title in metadata["by_title"].keys():
        if _is_month_sheet_title(title):
            month_titles.append(title)

    if not month_titles:
        return None

    month_titles.sort()
    return month_titles[-1]


def _is_month_sheet_title(title: str) -> bool:
    # YYYY.MM 형식의 월시트명인지 확인
    parts = title.split(".")
    if len(parts) != 2:
        return False

    yyyy_str, mm_str = parts

    if len(yyyy_str) != 4 or not yyyy_str.isdigit():
        return False

    if len(mm_str) != 2 or not mm_str.isdigit():
        return False

    mm = int(mm_str)
    return 1 <= mm <= 12


def _add_sheet(
    service,
    spreadsheet_id: str,
    sheet_title: str,
    insert_index: int,
) -> int:
    # 지정한 위치(index)에 새 시트 생성
    body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": sheet_title,
                        "index": insert_index,
                    }
                }
            }
        ]
    }

    response = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()

    replies = response.get("replies", [])
    return int(replies[0]["addSheet"]["properties"]["sheetId"])


def _copy_first_row_format(
    service,
    spreadsheet_id: str,
    source_sheet_id: int,
    destination_sheet_id: int,
) -> None:
    # 전달 시트의 1행 서식만 복사
    body = {
        "requests": [
            {
                "copyPaste": {
                    "source": {
                        "sheetId": source_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "destination": {
                        "sheetId": destination_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "pasteType": "PASTE_FORMAT",
                    "pasteOrientation": "NORMAL",
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()


def _freeze_first_row(service, spreadsheet_id: str, sheet_id: int) -> None:
    # 헤더 행(1행) 고정
    body = {
        "requests": [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "frozenRowCount": DEFAULT_FREEZE_ROWS,
                        },
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()


def _sort_by_report_date(
    service,
    spreadsheet_id: str,
    sheet_id: int,
    start_row_index: int,
    end_row_index: int,
    start_column_index: int,
    end_column_index: int,
) -> None:
    # 데이터 영역을 A열(report_date) 기준 오름차순 정렬
    body = {
        "requests": [
            {
                "sortRange": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row_index,
                        "endRowIndex": end_row_index,
                        "startColumnIndex": start_column_index,
                        "endColumnIndex": end_column_index,
                    },
                    "sortSpecs": [
                        {
                            "dimensionIndex": 0,
                            "sortOrder": "ASCENDING",
                        }
                    ],
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()


def _apply_data_borders(
    service,
    spreadsheet_id: str,
    sheet_id: int,
    start_row_index: int,
    end_row_index: int,
    start_column_index: int,
    end_column_index: int,
) -> None:
    # 데이터 영역 전체에 테두리 적용
    body = {
        "requests": [
            {
                "updateBorders": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row_index,
                        "endRowIndex": end_row_index,
                        "startColumnIndex": start_column_index,
                        "endColumnIndex": end_column_index,
                    },
                    "top": {"style": "SOLID"},
                    "bottom": {"style": "SOLID"},
                    "left": {"style": "SOLID"},
                    "right": {"style": "SOLID"},
                    "innerHorizontal": {"style": "SOLID"},
                    "innerVertical": {"style": "SOLID"},
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()


def _auto_resize_columns(
    service,
    spreadsheet_id: str,
    sheet_id: int,
    start_column_index: int,
    end_column_index: int,
) -> None:
    # 지정 열 구간 auto resize
    body = {
        "requests": [
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": start_column_index,
                        "endIndex": end_column_index,
                    }
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()


def _set_columns_width(
    service,
    spreadsheet_id: str,
    sheet_id: int,
    start_column_index: int,
    end_column_index: int,
    pixel_size: int,
) -> None:
    # 지정 열 구간 너비를 동일하게 설정
    body = {
        "requests": [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": start_column_index,
                        "endIndex": end_column_index,
                    },
                    "properties": {
                        "pixelSize": pixel_size,
                    },
                    "fields": "pixelSize",
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()


def _set_column_width(
    service,
    spreadsheet_id: str,
    sheet_id: int,
    column_index: int,
    pixel_size: int,
) -> None:
    # 단일 열 너비 설정
    body = {
        "requests": [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": column_index,
                        "endIndex": column_index + 1,
                    },
                    "properties": {
                        "pixelSize": pixel_size,
                    },
                    "fields": "pixelSize",
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()


def _get_column_width(
    service,
    spreadsheet_id: str,
    sheet_id: int,
) -> int:
    # 현재 E열(value)의 실제 너비 조회
    response = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        includeGridData=True,
        fields="sheets(properties(sheetId),data(columnMetadata(pixelSize)))",
    ).execute()

    sheets = response.get("sheets", [])
    for sheet in sheets:
        if int(sheet["properties"]["sheetId"]) != sheet_id:
            continue

        data_list = sheet.get("data", [])
        if not data_list:
            return DEFAULT_COLUMN_WIDTH

        column_meta = data_list[0].get("columnMetadata", [])
        if VALUE_COLUMN_INDEX >= len(column_meta):
            return DEFAULT_COLUMN_WIDTH

        return int(column_meta[VALUE_COLUMN_INDEX].get("pixelSize", DEFAULT_COLUMN_WIDTH))

    return DEFAULT_COLUMN_WIDTH