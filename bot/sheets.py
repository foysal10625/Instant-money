import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_gc = None
_sheet = None


def _get_sheet():
    global _gc, _sheet
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from config import GOOGLE_SHEET_ID, GOOGLE_SHEET_CREDENTIALS

        if not GOOGLE_SHEET_ID or not GOOGLE_SHEET_CREDENTIALS:
            return None

        if _sheet is not None:
            return _sheet

        creds_data = json.loads(GOOGLE_SHEET_CREDENTIALS)
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        try:
            ws = sh.worksheet("Task Approvals")
        except Exception:
            ws = sh.add_worksheet(title="Task Approvals", rows=1000, cols=10)
            ws.append_row(["User ID", "Username", "Task Name", "Reward", "Date", "Status"])
        _sheet = ws
        return _sheet
    except Exception as e:
        logger.warning(f"Google Sheets unavailable: {e}")
        return None


def log_approved_task(user_id: int, username: str, task_name: str, reward: float, status: str = "approved"):
    ws = _get_sheet()
    if ws is None:
        return False
    try:
        ws.append_row([
            user_id,
            username or "",
            task_name,
            reward,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status,
        ])
        return True
    except Exception as e:
        logger.warning(f"Failed to log to Google Sheets: {e}")
        return False
