import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_clients = {}   # cache: sheet_name → worksheet


def _get_worksheet(sheet_name: str):
    global _clients
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from config import GOOGLE_SHEET_ID, GOOGLE_SHEET_CREDENTIALS

        if not GOOGLE_SHEET_ID or not GOOGLE_SHEET_CREDENTIALS:
            return None

        if sheet_name in _clients:
            return _clients[sheet_name]

        creds_data = json.loads(GOOGLE_SHEET_CREDENTIALS)
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)

        headers = {
            "Instagram IDs": ["User ID", "TG Username", "Task", "Acc Username", "Password", "2FA Key", "Reward ($)", "Date"],
            "Facebook IDs":  ["UID", "Password", "2FA Key", "Date"],
        }

        try:
            ws = sh.worksheet(sheet_name)
        except Exception:
            ws = sh.add_worksheet(title=sheet_name, rows=5000, cols=10)
            if sheet_name in headers:
                ws.append_row(headers[sheet_name])

        _clients[sheet_name] = ws
        return ws
    except Exception as e:
        logger.warning(f"Google Sheets unavailable ({sheet_name}): {e}")
        return None


def log_submission(user_id: int, tg_username: str, task_title: str, task_type: str,
                   acc_username: str, acc_password: str, twofa_key: str, reward: float) -> bool:
    if task_type == "facebook":
        sheet_name = "Facebook IDs"
        ws = _get_worksheet(sheet_name)
        if ws is None:
            return False
        try:
            # Facebook format: UID - Password - 2FA Key - Date
            ws.append_row([
                acc_username,   # UID
                acc_password,   # Password
                twofa_key,      # 2FA Key
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ])
            return True
        except Exception as e:
            logger.warning(f"Sheet write failed ({sheet_name}): {e}")
            return False
    else:
        sheet_name = "Instagram IDs"
        ws = _get_worksheet(sheet_name)
        if ws is None:
            return False
        try:
            ws.append_row([
                user_id,
                tg_username or "",
                task_title,
                acc_username,
                acc_password,
                twofa_key,
                reward,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ])
            return True
        except Exception as e:
            logger.warning(f"Sheet write failed ({sheet_name}): {e}")
            return False
