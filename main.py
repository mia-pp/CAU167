"""
main.py
- CAU167 통합 진입점
- 인자가 없으면 Qt UI 실행
- 인자가 2개(start_date, end_date)면 기존 콘솔 실행
- 기존 엔진 구조(Function / Service / Config / Auth / Log)는 그대로 유지
"""

import os
import sys


# ==============================
# Constants
# ==============================
APP_VERSION = "1.1"  # 버전 변경 시 이 한 줄만 수정

# macOS에서는 knw_license.pyd를 사용할 수 없으므로 import 생략
if sys.platform != "darwin":
    import knw_license

from PyQt5.QtWidgets import QApplication

from Common.log import build_logger
from Function.config_loader import load_config
from Function.date_util import parse_yyyy_mm_dd
from Function.date_util import validate_date_range
from Function.path_util import get_base_dir
from Function.ui_main_window import MainWindow
from Service.orchestrator import run


def run_console() -> None:
    """
    콘솔 실행
    예:
        python main.py 2026-03-01 2026-03-05
    """
    base_dir = get_base_dir()
    config = load_config(base_dir)

    logger = build_logger(base_dir / config["log_dir"])

    try:
        if len(sys.argv) != 3:
            raise ValueError("인자 부족 또는 형식 오류: start_date end_date 필요 (예: 2026-03-01 2026-03-05)")

        start_date = parse_yyyy_mm_dd(sys.argv[1])
        end_date = parse_yyyy_mm_dd(sys.argv[2])
        validate_date_range(start_date, end_date)

        summary = run(
            base_dir=base_dir,
            config=config,
            logger=logger,
            start_date=start_date,
            end_date=end_date,
        )

        logger.info(
            f"DONE success_count={summary.get('success_count', 0)} "
            f"fail_count={summary.get('fail_count', 0)} "
            f"version={APP_VERSION}"
        )

    except Exception as e:
        logger.exception(f"FATAL {e}")
        sys.exit(1)


def run_ui() -> None:
    """
    Qt UI 실행
    예:
        python main.py
    """
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


def main() -> None:
    """
    실행 모드 분기
    - 인자 없음: UI 실행
    - 인자 2개: 콘솔 실행
    """
    if len(sys.argv) == 1:
        run_ui()
        return

    if len(sys.argv) == 3:
        run_console()
        return

    print("사용법:")
    print("  UI 실행: python main.py")
    print("  콘솔 실행: python main.py 2026-03-01 2026-03-05")
    sys.exit(1)


if __name__ == "__main__":
    main()