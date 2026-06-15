import logging
import random
import string
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import database as db
import sheets
from config import OWNER_ID, ADMIN_IDS, REFERRAL_BONUS_PERCENT

logger = logging.getLogger(__name__)

SELECTING_TASK = 1
CONFIRM_CREDENTIALS = 2
AWAITING_UID = 3
AWAITING_2FA = 4

MAIN_MENU = ReplyKeyboardMarkup(
    [["📋 Tasks", "💰 Balance"], ["👫 Refer", "💸 Withdraw"], ["👤 Profile"]],
    resize_keyboard=True,
)

PLATFORM_EMOJI = {"instagram": "📸", "facebook": "📘"}

_CONSONANTS = "bcdfghjklmnprstvwxz"
_VOWELS = "aeiou"


def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMIN_IDS


def get_task_system_enabled():
    import config
    return config.TASK_SYSTEM_ENABLED


def _syllable() -> str:
    patterns = [
        lambda: random.choice(_CONSONANTS) + random.choice(_VOWELS),
        lambda: random.choice(_CONSONANTS) + random.choice(_VOWELS) + random.choice(_CONSONANTS),
        lambda: random.choice(_CONSONANTS) + random.choice(_CONSONANTS) + random.choice(_VOWELS),
        lambda: random.choice(_VOWELS) + random.choice(_CONSONANTS),
    ]
    return random.choice(patterns)()


def _word(min_syl: int = 1, max_syl: int = 3) -> str:
    return "".join(_syllable() for _ in range(random.randint(min_syl, max_syl)))


def _nums(min_len: int = 1, max_len: int = 3) -> str:
    return "".join(random.choices(string.digits, k=random.randint(min_len, max_len)))


def generate_username() -> str:
    """Generate a unique, human-looking Instagram username."""
    structures = [
        lambda: f"{_word(1,2)}{_nums(2,3)}.{_word(1,2)}{_nums(1,2)}",
        lambda: f"{_word(1,2)}.{_word(1,2)}{_nums(2,3)}",
        lambda: f"{_word(2,3)}{_nums(2,3)}.{_word(1,2)}",
        lambda: f"{_word(1,2)}{_nums(1,2)}{_word(1,2)}.{_nums(1,3)}",
        lambda: f"{_word(2,3)}.{_word(1,2)}{_nums(2,4)}",
    ]
    candidate = random.choice(structures)()
    while db.is_acc_username_taken(candidate):
        candidate = random.choice(structures)()
    return candidate


async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    if not u or u.get("is_banned"):
        await update.message.reply_text("🚫 You are banned.")
        return ConversationHandler.END

    if not get_task_system_enabled():
        await update.message.reply_text(
            "⚠️ The task system is currently disabled. Check back later!",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    tasks = db.get_active_tasks()
    if not tasks:
        await update.message.reply_text(
            "📋 No tasks available right now. Check back later!",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    context.user_data["tasks_map"] = {t["title"]: t for t in tasks}
    buttons = []
    for t in tasks:
        emoji = PLATFORM_EMOJI.get(t.get("task_type", "instagram"), "📌")
        buttons.append([f"{emoji} {t['title']} (${t['reward']:.4f})"])
    buttons.append(["❌ Cancel"])

    await update.message.reply_text(
        "📋 *Available Tasks*\n\nSelect a task to complete:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True),
    )
    return SELECTING_TASK


async def task_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    tasks_map = context.user_data.get("tasks_map", {})
    selected_task = None
    for title, task in tasks_map.items():
        emoji = PLATFORM_EMOJI.get(task.get("task_type", "instagram"), "📌")
        if f"{emoji} {title} (${task['reward']:.4f})" == text:
            selected_task = task
            break

    if not selected_task:
        await update.message.reply_text("Please select a valid task from the list.")
        return SELECTING_TASK

    task_type = selected_task.get("task_type", "instagram")
    task_password = selected_task.get("task_password", "")
    context.user_data["selected_task"] = selected_task

    if task_type == "facebook":
        # Facebook: only give password, no username generated here
        await update.message.reply_text(
            f"📘 *{selected_task['title']}*\n\n"
            f"{selected_task.get('description', '')}\n\n"
            f"💰 Reward: `${selected_task['reward']:.4f}`\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 *Create your Facebook account using this password:*\n\n"
            f"🔑 Password: `{task_password}`\n\n"
            f"✅ Once you've created the account and enabled 2FA, press *I'm Ready*.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["✅ I'm Ready"], ["❌ Cancel"]],
                resize_keyboard=True,
            ),
        )
    else:
        # Instagram: generate unique username + give password
        generated_username = generate_username()
        context.user_data["generated_username"] = generated_username
        await update.message.reply_text(
            f"📸 *{selected_task['title']}*\n\n"
            f"{selected_task.get('description', '')}\n\n"
            f"💰 Reward: `${selected_task['reward']:.4f}`\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 *Use these credentials to create your Instagram account:*\n\n"
            f"👤 Username: `{generated_username}`\n"
            f"🔑 Password: `{task_password}`\n\n"
            f"✅ Once you've created the account and enabled 2FA, press *I'm Ready* to submit your 2FA key.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["✅ I'm Ready"], ["❌ Cancel"]],
                resize_keyboard=True,
            ),
        )
    return CONFIRM_CREDENTIALS


async def user_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    if "Ready" not in text and "ready" not in text:
        await update.message.reply_text(
            "Please press the *✅ I'm Ready* button when you have created the account.",
            parse_mode="Markdown",
        )
        return CONFIRM_CREDENTIALS

    task = context.user_data.get("selected_task", {})
    task_type = task.get("task_type", "instagram")

    if task_type == "facebook":
        await update.message.reply_text(
            "🆔 *Step 1: Enter your Facebook UID*\n\n"
            "Please enter the *UID* of the Facebook account you just created:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        )
        return AWAITING_UID
    else:
        await update.message.reply_text(
            "🔐 *Step: Enter your 2FA Key*\n\n"
            "Please enter the *2FA backup code* or *TOTP secret key* from your authenticator app:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        )
        return AWAITING_2FA


async def receive_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    uid = update.message.text.strip()
    if not uid:
        await update.message.reply_text("Please enter a valid UID.")
        return AWAITING_UID

    context.user_data["fb_uid"] = uid

    await update.message.reply_text(
        "🔐 *Step 2: Enter your 2FA Key*\n\n"
        "Please enter the *2FA backup code* or *TOTP secret key* from your authenticator app:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return AWAITING_2FA


async def receive_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    user = update.effective_user
    task = context.user_data.get("selected_task")

    if not task:
        await update.message.reply_text("Something went wrong. Please try again.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    task_type = task.get("task_type", "instagram")
    twofa_key = update.message.text.strip()
    acc_password = task.get("task_password", "")
    tg_username = user.username or user.first_name or str(user.id)

    if task_type == "facebook":
        acc_username = context.user_data.get("fb_uid", "")
    else:
        acc_username = context.user_data.get("generated_username", "")

    await update.message.reply_text(
        "✅ *Your report has been received!*\n\n"
        "Please wait while our team verifies your account.\n"
        "Your balance will be updated once the Live ID verification is complete. 🕐",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )

    sub_id = db.create_submission(
        user.id, task["task_id"], acc_username, acc_password, twofa_key
    )
    db.update_submission_status(sub_id, "approved", 0)

    try:
        logged = sheets.log_submission(
            user.id, tg_username, task["title"], task_type,
            acc_username, acc_password, twofa_key, task["reward"],
        )
        if logged:
            db.mark_submission_logged(sub_id)
    except Exception as e:
        logger.warning(f"Sheet logging failed: {e}")

    referral = db.get_referral_by_referred(user.id)
    if referral and not referral.get("task_completed"):
        db.mark_referral_completed(user.id, 0)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


task_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📋 Tasks$"), show_tasks)],
    states={
        SELECTING_TASK:      [MessageHandler(filters.TEXT & ~filters.COMMAND, task_selected)],
        CONFIRM_CREDENTIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_ready)],
        AWAITING_UID:        [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_uid)],
        AWAITING_2FA:        [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_2fa)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CommandHandler("start", cancel),
        MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
    ],
    allow_reentry=True,
)
