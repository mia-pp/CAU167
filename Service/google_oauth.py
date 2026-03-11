"""
Service/google_oauth.py
- 사용자 토큰(OAuth) 방식 인증 처리
- Auth/client_secret.json: 사용자가 제공
- 최초 실행 시 브라우저 인증 → Auth/token.json 자동 생성
- 이후 재실행은 token 재사용(만료 시 refresh)
- token.json 공유 금지
- 프로그램은 실행 위치 기준으로 Auth/를 찾는다
"""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# ==============================
# Constants
# ==============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_credentials(base_dir: Path, auth_dir_name: str) -> Credentials:
    auth_dir = base_dir / auth_dir_name
    auth_dir.mkdir(parents=True, exist_ok=True)

    client_secret_path = auth_dir / "client_secret.json"
    token_path = auth_dir / "token.json"

    if not client_secret_path.exists():
        raise FileNotFoundError(f"OAuth client_secret.json이 없습니다: {client_secret_path}")

    creds = None

    # 1) 기존 token.json이 있으면 재사용
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # 2) 유효하지 않으면 refresh 또는 신규 인증
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds