# CAU167 - 그레이 키워드 적중률 분석 자동화

> **ver 1.1**

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
- 404 응답 시 재시도 없이 즉시 해당 날짜 실패 처리
- 그 외 오류(네트워크, 서버 오류 등)는 최대 3회 재시도
- 동일 날짜 파일이 이미 있으면 삭제 후 재저장. 파일이 잠겨 있으면 대체 파일명으로 저장

### 2-2. CSV 파싱
- 인코딩 fallback 지원: `utf-8-sig` → `utf-8` → `euc-kr`
- CSV 원본 컬럼 중 `No`, `name` 컬럼은 제외
- 숫자 컬럼(`key`, `count`)은 `int`로 변환하여 Google Sheets에 숫자 타입으로 적재
  - 문자열 그대로 적재 시 `'` 접두사 문제 발생하므로 파싱 단계에서 처리
- Google Sheets 입력 컬럼:

  | 컬럼 | 타입 | 설명 |
  |---|---|---|
  | `report_date` | str | 취합 날짜 (YYYY-MM-DD) |
  | `collection` | str | 컬렉션 |
  | `key` | int | 키 ID |
  | `target` | str | 타겟 |
  | `value` | str | 값 |
  | `tag` | str | 태그 |
  | `count` | int | 카운트 |

### 2-3. Google Sheets 적재
- 월별 시트명 형식: `YYYY.MM`
- 시트가 없으면 생성, 전달 시트가 있으면 전달 오른쪽에 생성
- 전달 시트의 **1행 서식만 복사**, 헤더 입력 후 **1행 고정**
- 재실행 시 실행 구간 데이터만 비우고 빈행 정리 후 다시 적재 (멱등성)
- 빈행 정리(compact) 시에도 숫자 컬럼 타입 유지

### 2-4. UI 실행
- 시작일 / 종료일 선택
- 실행 버튼 클릭 시 별도 프로세스로 엔진 실행
- 진행 상태 / 결과 / 로그 확인 가능
- 로그 폴더 열기 / 다운로드 폴더 열기 버튼 제공

---

## 3. 프로젝트 구조

```text
CAU167/
├─ Auth/
│  ├─ client_secret.json           → Google OAuth 인증용 클라이언트 파일
│  └─ token.json                   → OAuth 토큰 (최초 실행 후 자동 생성)
├─ Common/
│  └─ log.py                       → 로그
├─ Config/
│  └─ google_sheet_config.json     → 구글 시트 설정
├─ downloads/
│  └─ YYYY-MM-DD_keyword_report_athena.csv
│                                  → 날짜별 다운로드 CSV 저장 폴더 (자동 생성)
├─ Function/
│  ├─ config_loader.py             → 설정 파일 로드
│  ├─ csv_util.py                  → CSV 인코딩 처리 / 헤더 검증 / 데이터 파싱 / 숫자 타입 변환
│  ├─ date_util.py                 → 날짜 파싱 / 기간 검증 / 날짜 반복 처리
│  ├─ path_util.py                 → 실행 위치 기준 base_dir 계산
│  ├─ ui_log_helper.py             → UI 로그 필터링 / 문구 정규화
│  └─ ui_main_window.py            → Qt UI 로드 / 실행 버튼 / 로그 표시 / 프로세스 제어
├─ Log/
│  └─ log_YYYYMMDD.log             → 실행 로그 파일 (자동 생성)
├─ Resource/
│  ├─ icon.ico                     → 프로그램 아이콘
│  └─ main.ui                      → Qt Designer UI 파일
├─ Service/
│  ├─ downloader.py                → 날짜별 CSV 다운로드 / 404 즉시 실패 / 재시도 처리
│  ├─ google_oauth.py              → OAuth 인증 / token 재사용
│  ├─ orchestrator.py              → 전체 실행 흐름 제어
│  └─ sheet_writer.py              → 월 시트 생성 / 값 비우기 / 빈행 정리 / 시트 적재 / 서식 반영
├─ main.py
└─ requirements.txt
```

---

## 4. 설정 파일

### Config/google_sheet_config.json

```json
{
  "sheet_id": "구글 시트 ID",
  "auth_dir": "Auth",
  "log_dir": "Log",
  "downloads_dir": "downloads",
  "sheet_name_format": "{yyyy}.{mm}",
  "headers": ["report_date", "collection", "key", "target", "value", "tag", "count"]
}
```

### Auth/client_secret.json
- Google Cloud Console에서 발급한 OAuth 클라이언트 파일
- 최초 실행 시 브라우저 인증 후 `token.json` 자동 생성
- `token.json`은 공유 금지

---

## 5. 실행 방법

### UI 실행
```bash
python main.py
```

### 콘솔 실행
```bash
python main.py 2026-03-01 2026-03-05
```

### 날짜 입력 규칙
- 형식: `YYYY-MM-DD`
- 종료일은 실행일 전날까지만 허용
- 시작일 > 종료일 차단
- 1년 이상 기간 차단

---

## 6. 로그

| 로그 키워드 | 의미 |
|---|---|
| `OK[DATE=...]` | 해당 날짜 처리 성공 |
| `FAIL[DATE=...]` | 해당 날짜 처리 실패 (사유 코드 포함) |
| `WARN[DATE=...]` | 경고 (비정상 행 스킵, 헤더 불일치 등) |
| `SHEET_CREATED` | 월 시트 신규 생성 |
| `SHEET_EXISTS` | 기존 월 시트 재사용 |
| `SHEET_CLEARED` | 실행 구간 데이터 비움 |
| `SHEET_COMPACTED` | 빈행 정리 완료 |
| `SHEET_WRITE_OK` | 시트 적재 완료 |
| `DONE success_count=N fail_count=N` | 전체 실행 결과 요약 |
| `FATAL` | 치명적 오류 (프로세스 종료) |

> `success_count`: CSV 파싱 성공 날짜 수 (다운로드 + 파싱 모두 성공)  
> `fail_count`: 다운로드 실패 + 파싱 실패 날짜 수 + 시트 write 실패 수

---

## 7. 빌드

### 환경
- Python 3.9
- PyInstaller 5.13.2 (pyarmor 8.5.12 호환 버전)

### 빌드 명령어 (Windows)

```powershell
# 1. 콘솔 버전으로 테스트 빌드
venv\Scripts\pyinstaller `
  --noconfirm --clean --onefile `
  --name CAU167 `
  --icon "Resource\icon.ico" `
  --add-binary "knw_license.pyd;." `
  --add-binary "venv\lib\site-packages\netifaces.cp39-win_amd64.pyd;." `
  --add-data "Config;Config" `
  --add-data "Resource;Resource" `
  --hidden-import=netifaces `
  main.py

# 2. 정상 실행 확인 후 --noconsole 추가하여 최종 빌드
# 3. pyarmor 난독화
pyarmor gen --pack dist\CAU167.exe -r main.py Common/ Function/ Service/
```

> `netifaces` 경로 확인: `venv\Scripts\python.exe -c "import netifaces; print(netifaces.__file__)"`

### 배포 구성

```text
배포폴더/
├─ CAU167.exe
├─ Config/
│  └─ google_sheet_config.json
└─ Auth/
   └─ client_secret.json
```

`Auth/token.json`, `Log/`, `downloads/`는 실행 후 자동 생성.

---

## 8. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| 1.0 | - | 최초 릴리스 |
| 1.1 | 2026-04-13 | CSV 숫자 컬럼(`key`, `count`) `int` 변환 처리 추가 (Google Sheets `'` 접두사 문제 수정) / compact 재write 시 숫자 타입 유지 / 404 즉시 실패 반환으로 변경 / 프로세스 종료 후 마지막 로그 flush 추가 / UI 진행 단계 dead 항목 정리 |