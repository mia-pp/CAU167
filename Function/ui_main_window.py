"""
ui_main_window.py
- Qt Designer의 Resource/main.ui를 로드
- 실행 버튼 클릭 시
  - 개발 환경: python main.py start_date end_date
  - 패키징 환경: 현재 앱 실행파일 start_date end_date
  로 별도 프로세스를 실행
- Resource/icon.ico 또는 icon.icns가 있으면 창 아이콘 적용
- 작업 완료 후에도 UI 창은 닫히지 않고 유지
- 완료 후 최신 로그 파일에서 success_count / fail_count를 읽어 UI에 반영
- 실패 시 최신 로그 파일의 마지막 에러 메시지를 결과창에 표시
- UI 로그창에는 핵심 로그만 필터링해서 깔끔하게 표시
"""

import os
import sys
from pathlib import Path

from PyQt5 import uic
from PyQt5.QtCore import QDate
from PyQt5.QtCore import QProcess
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QMessageBox

from Function.config_loader import load_config
from Function.path_util import get_base_dir
from Function.ui_log_helper import normalize_log_line
from Function.ui_log_helper import should_display_log_line


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        resource_dir = self._get_resource_dir()
        ui_path = resource_dir / "main.ui"
        icon_icns_path = resource_dir / "icon.icns"
        icon_ico_path = resource_dir / "icon.ico"

        uic.loadUi(str(ui_path), self)

        if icon_icns_path.exists():
            self.setWindowIcon(QIcon(str(icon_icns_path)))
        elif icon_ico_path.exists():
            self.setWindowIcon(QIcon(str(icon_ico_path)))

        self.base_dir = get_base_dir()
        self.config = load_config(self.base_dir)

        self.process = None
        self.is_running = False
        self.last_log_position = 0
        self.last_ui_log_line = ""

        self.log_poll_timer = QTimer(self)
        self.log_poll_timer.timeout.connect(self.read_latest_log_lines)

        self._setup_ui()
        self._connect_signals()

    def _get_resource_dir(self) -> Path:
        """
        개발 환경 / PyInstaller 패키징 환경 모두 대응
        """
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / "Resource"

        return Path(__file__).resolve().parents[1] / "Resource"

    def _setup_ui(self) -> None:
        today = QDate.currentDate()
        yesterday = today.addDays(-1)

        self.date_start.setDate(yesterday)
        self.date_end.setDate(yesterday)

        self.label_status.setText("상태: 대기중")
        self.label_current_task.setText("현재 작업: -")
        self.label_success_count.setText("성공: 0건")
        self.label_fail_count.setText("실패: 0건")
        self.progress_run.setValue(0)

        self.text_result.clear()
        self.text_log.clear()
        self.btn_run.setEnabled(True)

    def _connect_signals(self) -> None:
        self.btn_run.clicked.connect(self.run_process)
        self.btn_reset.clicked.connect(self.reset_ui)
        self.btn_open_log_folder.clicked.connect(self.open_log_folder)
        self.btn_open_download_folder.clicked.connect(self.open_download_folder)

    def run_process(self) -> None:
        if self.is_running:
            QMessageBox.warning(self, "실행중", "이미 실행 중입니다.")
            return

        if not self._validate_dates():
            return

        start_date = self.date_start.date().toString("yyyy-MM-dd")
        end_date = self.date_end.date().toString("yyyy-MM-dd")

        self.text_result.clear()
        self.text_log.clear()
        self.label_status.setText("상태: 실행중")
        self.label_current_task.setText("현재 작업: 실행 시작")
        self.label_success_count.setText("성공: -")
        self.label_fail_count.setText("실패: -")
        self.progress_run.setValue(5)

        self.is_running = True
        self.btn_run.setEnabled(False)
        self.last_ui_log_line = ""
        self.last_log_position = self._get_current_log_file_size()

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(self.base_dir))

        if getattr(sys, "frozen", False):
            # 패키징된 앱에서는 현재 실행파일 자신을 다시 호출
            self.process.setProgram(sys.executable)
            self.process.setArguments([start_date, end_date])
            self.append_log(f"프로세스 시작(패키징): {sys.executable} {start_date} {end_date}")
        else:
            # 개발 환경에서는 python main.py 형태로 실행
            self.process.setProgram(sys.executable)
            self.process.setArguments(
                [
                    str(self.base_dir / "main.py"),
                    start_date,
                    end_date,
                ]
            )
            self.append_log(f"프로세스 시작(개발): {sys.executable} main.py {start_date} {end_date}")

        self.process.finished.connect(self.on_process_finished)
        self.process.errorOccurred.connect(self.on_process_error)

        self.process.start()
        self.log_poll_timer.start(500)

    def reset_ui(self) -> None:
        if self.is_running:
            QMessageBox.warning(self, "실행중", "실행 중에는 초기화할 수 없습니다.")
            return

        self._setup_ui()

    def open_log_folder(self) -> None:
        self._open_folder(self.base_dir / self.config["log_dir"])

    def open_download_folder(self) -> None:
        self._open_folder(self.base_dir / self.config["downloads_dir"])

    def _open_folder(self, folder_path: Path) -> None:
        folder_path.mkdir(parents=True, exist_ok=True)

        if sys.platform.startswith("win"):
            os.startfile(str(folder_path))
        elif sys.platform == "darwin":
            os.system(f'open "{folder_path}"')
        else:
            os.system(f'xdg-open "{folder_path}"')

    def _validate_dates(self) -> bool:
        start_qdate = self.date_start.date()
        end_qdate = self.date_end.date()
        today = QDate.currentDate()

        if start_qdate > end_qdate:
            QMessageBox.warning(self, "날짜 오류", "취합 시작일이 종료일보다 클 수 없습니다.")
            return False

        if end_qdate >= today:
            QMessageBox.warning(self, "날짜 오류", "취합 종료일은 실행일 전날까지만 가능합니다.")
            return False

        if start_qdate.daysTo(end_qdate) >= 365:
            QMessageBox.warning(self, "날짜 오류", "취합 기간은 1년 미만만 가능합니다.")
            return False

        return True

    def read_latest_log_lines(self) -> None:
        latest_log = self._get_latest_log_file()
        if latest_log is None:
            return

        try:
            with latest_log.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self.last_log_position)
                new_text = f.read()
                self.last_log_position = f.tell()

            if not new_text.strip():
                return

            for raw_line in new_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                if not should_display_log_line(line):
                    continue

                normalized = normalize_log_line(line)
                self.append_log(normalized)
                self._update_progress_from_log(normalized)

        except Exception as e:
            self.append_log(f"로그 파일 읽기 오류: {e}")

    def _update_progress_from_log(self, line: str) -> None:
        progress = self.progress_run.value()

        if "라이센스 확인" in line:
            progress = max(progress, 5)
            self.label_current_task.setText("현재 작업: 라이센스 확인")

        elif "Google 인증" in line:
            progress = max(progress, 15)
            self.label_current_task.setText("현재 작업: Google 인증")

        elif "시트 메타 조회" in line:
            progress = max(progress, 20)
            self.label_current_task.setText("현재 작업: 시트 메타 조회")

        elif "CSV 다운로드 완료" in line:
            progress = min(max(progress + 5, 25), 70)
            self.label_current_task.setText("현재 작업: CSV 다운로드")

        elif "CSV 파싱 완료" in line:
            progress = min(max(progress + 5, 30), 75)
            self.label_current_task.setText("현재 작업: CSV 파싱")

        elif "기존 시트 사용" in line or "시트 생성 완료" in line:
            progress = min(max(progress + 5, 75), 85)
            self.label_current_task.setText("현재 작업: 시트 준비")

        elif "값 비움" in line:
            progress = min(max(progress + 5, 80), 90)
            self.label_current_task.setText("현재 작업: 기존 데이터 비우기")

        elif "빈행 정리" in line:
            progress = min(max(progress + 5, 85), 92)
            self.label_current_task.setText("현재 작업: 빈행 정리")

        elif "기존 데이터 삭제" in line:
            progress = min(max(progress + 5, 80), 90)
            self.label_current_task.setText("현재 작업: 기존 데이터 정리")

        elif "시트 적재 완료" in line:
            progress = min(max(progress + 5, 90), 95)
            self.label_current_task.setText("현재 작업: 시트 적재")

        elif "완료: 성공" in line:
            progress = 100
            self.label_current_task.setText("현재 작업: 완료")

        self.progress_run.setValue(self._round_to_5(progress))

    def _round_to_5(self, value: int) -> int:
        rounded = int(round(value / 5.0) * 5)
        if rounded < 0:
            return 0
        if rounded > 100:
            return 100
        return rounded

    def _get_latest_log_file(self):
        log_dir = self.base_dir / self.config["log_dir"]
        if not log_dir.exists():
            return None

        log_files = sorted(log_dir.glob("log_*.log"))
        if not log_files:
            return None

        return log_files[-1]

    def _get_current_log_file_size(self) -> int:
        latest_log = self._get_latest_log_file()
        if latest_log is None or not latest_log.exists():
            return 0

        try:
            return latest_log.stat().st_size
        except Exception:
            return 0

    def _update_counts_from_log_file(self) -> None:
        latest_log = self._get_latest_log_file()
        if latest_log is None:
            return

        try:
            lines = latest_log.read_text(encoding="utf-8", errors="replace").splitlines()

            success_count = None
            fail_count = None

            for line in reversed(lines):
                if "DONE success_count=" in line and "fail_count=" in line:
                    try:
                        after_done = line.split("DONE success_count=", 1)[1]
                        success_part, fail_part = after_done.split(" fail_count=", 1)

                        success_count = int(success_part.strip())
                        fail_count = int(fail_part.strip())
                        break
                    except Exception:
                        pass

            if success_count is not None and fail_count is not None:
                self.label_success_count.setText(f"성공: {success_count}건")
                self.label_fail_count.setText(f"실패: {fail_count}건")

        except Exception as e:
            self.append_log(f"로그 카운트 읽기 오류: {e}")

    def _get_last_error_from_log_file(self) -> str:
        latest_log = self._get_latest_log_file()
        if latest_log is None:
            return ""

        try:
            lines = latest_log.read_text(encoding="utf-8", errors="replace").splitlines()

            error_keywords = ["FATAL", "FAIL[", "Exception", "ERROR |"]
            for line in reversed(lines):
                if any(keyword in line for keyword in error_keywords):
                    return normalize_log_line(line)

        except Exception as e:
            return f"로그 에러 읽기 실패: {e}"

        return ""

    def on_process_finished(self, exit_code: int, exit_status) -> None:
        self.log_poll_timer.stop()

        self.is_running = False
        self.btn_run.setEnabled(True)

        if exit_code == 0:
            self._update_counts_from_log_file()
            self.label_status.setText("상태: 완료")
            self.label_current_task.setText("현재 작업: 완료")
            self.progress_run.setValue(100)
            self.append_result("실행이 완료되었습니다.")
        else:
            self.label_status.setText("상태: 실패")
            last_error = self._get_last_error_from_log_file()

            if last_error:
                self.append_result(f"[실패] {last_error}")
            else:
                self.append_result(f"[실패] 프로세스 종료 코드: {exit_code}")

        self.append_log(f"프로세스 종료 | exit_code={exit_code}")
        self.process = None

    def on_process_error(self, error) -> None:
        self.log_poll_timer.stop()

        self.is_running = False
        self.btn_run.setEnabled(True)
        self.label_status.setText("상태: 실패")
        self.append_result(f"[실패] 프로세스 실행 오류: {error}")
        self.append_log(f"프로세스 실행 오류: {error}")

    def append_log(self, message: str) -> None:
        if not message:
            return

        if message == self.last_ui_log_line:
            return

        self.text_log.appendPlainText(message)
        self.last_ui_log_line = message

    def append_result(self, message: str) -> None:
        self.text_result.append(message)

    def closeEvent(self, event) -> None:
        if self.is_running:
            QMessageBox.warning(self, "실행중", "작업이 끝난 후 창을 닫아주세요.")
            event.ignore()
            return

        event.accept()