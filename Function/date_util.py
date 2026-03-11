"""
Function/date_util.py
- 날짜 문자열 파싱(YYYY-MM-DD)
- 취합 기간 검증
  - 종료일은 실행일 전날까지만 허용
  - 시작일 > 종료일 차단
  - 1년 이상 기간 차단
- 기간 내 날짜 iterator 제공
"""

from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Iterator


def parse_yyyy_mm_dd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def validate_date_range(start_date: date, end_date: date) -> None:
    today = date.today()

    if start_date > end_date:
        raise ValueError("시작일이 종료일보다 큽니다.")

    if end_date >= today:
        raise ValueError("취합 종료일은 실행일 전날까지만 가능합니다.")

    if (end_date - start_date).days >= 365:
        raise ValueError("기간이 너무 깁니다. (1년 이상은 차단)")


def daterange(start_date: date, end_date: date) -> Iterator[date]:
    cur = start_date
    while cur <= end_date:
        yield cur
        cur += timedelta(days=1)