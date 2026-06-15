import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

ADMIN_IDS = []

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_CREDENTIALS = os.environ.get("GOOGLE_SHEET_CREDENTIALS", "")

MIN_WITHDRAW = float(os.environ.get("MIN_WITHDRAW", "1.0"))

TASK_SYSTEM_ENABLED = True
WITHDRAW_SYSTEM_ENABLED = True

LIVE_ID_BONUS_PER_ID = float(os.environ.get("LIVE_ID_BONUS_PER_ID", "0.05"))

WITHDRAW_METHODS = ["USD BEP20", "bKash Personal Number"]

ADMIN_CAN_CREATE_TASKS = True
OWNER_CAN_TOGGLE_TASKS = True

REFERRAL_BONUS_PERCENT = 20

DB_PATH = "bot/data/bot.db"
