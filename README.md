# CAU167 - 그레이 키워드 적중률 분석 자동화

## 1. 프로젝트 개요
CAU167은 날짜 범위 기준으로 규칙적인 URL의 CSV 파일을 다운로드하고,  
CSV 데이터를 가공하여 Google Sheets의 월별 시트(`YYYY.MM`)에 적재하는 Python 자동화 프로젝트입니다.

Qt Designer 기반 UI를 통해 사용자가 날짜 범위를 입력하고 실행할 수 있으며,  
실제 데이터 처리 로직은 별도 프로세스로 실행되어 UI 안정성을 유지합니다.

---

## 2. 주요 기능

### 2-1. CSV 다운로드
- 날짜 범위(`취합 시작일 ~ 취합 종료일`) 기준으로 CSV 다운로드
- URL 규칙:
  - `http://intwg.kakaocdn.net/clean_image/sapiens/report/YYYY-MM-DD_keyword_report_athena.csv`
- 파일이 없을 경우 404 처리
- 동일 날짜 파일이 이미 있으면 덮어쓰기 기준으로 처리

### 2-2. CSV 파싱
- 인코딩 fallback 지원
  - `utf-8-sig`
  - `utf-8`
  - `euc-kr`
- CSV 원본 컬럼 중 `name` 컬럼은 제외
- Google Sheets 입력 컬럼:
  - `report_date`
  - `collection`
  - `key`
  - `target`
  - `value`
  - `tag`
  - `count`

### 2-3. Google Sheets 적재
- 월별 시트명 형식: `YYYY.MM`
- 시트가 없으면 생성
- 전달 시트가 있으면 전달 오른쪽에 생성
- 전달 시트의 **1행 서식만 복사**
- 헤더 입력 후 **1행 고정**
- 재실행 시 실행 구간 데이터만 비우고 빈행 정리 후 다시 적재

### 2-4. UI 실행
- 시작일 / 종료일 선택
- 실행 버튼 클릭 시 별도 프로세스로 엔진 실행
- 진행 상태 / 결과 / 로그 확인 가능
- 로그 폴더 열기 / 다운로드 폴더 열기 버튼 제공

---

## 3. 프로젝트 구조

## 프로젝트 구조

```text
CAU167/
├─ Auth/
│  ├─ client_secret.json           → Google OAuth 인증용 클라이언트 파일
│  └─ token.json                   → OAuth 토큰
├─ Common/
│  └─ log.py                       → 로그
├─ Config/
│  └─ google_sheet_config.json     → 구글 시트 설정
├─ downloads/
│  └─ YYYY-MM-DD_keyword_report_athena.csv
│                                  → 날짜별 다운로드 CSV 저장 폴더
├─ Function/
│  ├─ config_loader.py             → 설정 파일 로드
│  ├─ csv_util.py                  → CSV 인코딩 처리 / 헤더 검증 / 데이터 파싱
│  ├─ date_util.py                 → 날짜 파싱 / 기간 검증 / 날짜 반복 처리
│  ├─ path_util.py                 → 실행 위치 기준 base_dir 계산
│  ├─ ui_log_helper.py             → UI 로그 필터링 / 문구 정규화
│  └─ ui_main_window.py            → Qt UI 로드 / 실행 버튼 / 로그 표시 / 프로세스 제어
├─ Log/
│  └─ log_YYYYMMDD.log             → 실행 로그 파일
├─ Resource/
│  ├─ icon.ico                     → 프로그램 아이콘
│  └─ main.ui                      → Qt Designer UI 파일
├─ Service/
│  ├─ downloader.py                → 날짜별 CSV 다운로드 / 재시도 처리
│  ├─ google_oauth.py              → OAuth 인증 / token 재사용
│  ├─ orchestrator.py              → 전체 실행 흐름 제어
│  └─ sheet_writer.py              → 월 시트 생성 / 값 비우기 / 빈행 정리 / 시트 적재 / 서식 반영
├─ main.py
└─ requirements.txt