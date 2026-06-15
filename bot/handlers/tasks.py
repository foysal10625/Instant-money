import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import database as db
import sheets
from config import OWNER_ID, ADMIN_IDS, REFERRAL_BONUS_PERCENT

logger = logging.getLogger(__name__)

SELECTING_TASK = 1
AWAITING_PROOF = 2

MAIN_MENU = ReplyKeyboardMarkup(
    [["📋 Tasks", "💰 Balance"], ["👫 Refer", "💸 Withdraw"], ["👤 Profile"]],
    resize_keyboard=True,
)


def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMIN_IDS


def get_task_system_enabled():
    import config
    return config.TASK_SYSTEM_ENABLED


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
    buttons = [[f"📌 {t['title']} (${t['reward']:.4f})"] for t in tasks]
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
        if f"📌 {title} (${task['reward']:.4f})" == text:
            selected_task = task
            break

    if not selected_task:
        await update.message.reply_text("Please select a valid task from the list.")
        return SELECTING_TASK

    context.user_data["selected_task"] = selected_task

    await update.message.reply_text(
        f"📌 *{selected_task['title']}*\n\n"
        f"{selected_task.get('description', 'No description.')}\n\n"
        f"💰 Reward: `${selected_task['reward']:.4f}`\n\n"
        f"📸 Submit your proof (screenshot, ID, or text):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return AWAITING_PROOF


async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    task = context.user_data.get("selected_task")
    if not task:
        await update.message.reply_text("Something went wrong. Please try again.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    proof = None
    proof_type = "text"
    if update.message.photo:
        proof = update.message.photo[-1].file_id
        proof_type = "photo"
    elif update.message.document:
        proof = update.message.document.file_id
        proof_type = "document"
    elif update.message.text:
        proof = update.message.text
        proof_type = "text"

    if not proof:
        await update.message.reply_text("Please send a valid proof (image, document, or text).")
        return AWAITING_PROOF

    sub_id = db.create_submission(user.id, task["task_id"], proof)

    db.update_submission_status(sub_id, "approved", 0)
    reward = task["reward"]
    db.update_user_balance(user.id, reward, "balance")
    db.add_transaction(user.id, "task_reward", reward, f"Task: {task['title']}")

    u = db.get_user(user.id)
    username = user.username or user.first_name or str(user.id)

    try:
        logged = sheets.log_approved_task(
            user.id,
            username,
            task["title"],
            reward,
            proof if proof_type == "text" else proof_type,
        )
        if logged:
            db.mark_submission_logged(sub_id)
    except Exception as e:
        logger.warning(f"Sheet logging failed: {e}")

    referral = db.get_referral_by_referred(user.id)
    if referral and not referral.get("task_completed"):
        bonus = round(reward * REFERRAL_BONUS_PERCENT / 100, 6)
        db.update_user_balance(referral["referrer_id"], bonus, "referral_bonus")
        db.mark_referral_completed(user.id, bonus)
        db.add_transaction(referral["referrer_id"], "referral_bonus", bonus, f"Referral bonus from {user.id}")
        try:
            await context.bot.send_message(
                referral["referrer_id"],
                f"🎉 Your referred user completed a task!\nYou earned `${bonus:.4f}` referral bonus.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ *Task Completed!*\n\n"
        f"Task: *{task['title']}*\n"
        f"💰 `${reward:.4f}` has been added to your balance instantly!",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


task_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📋 Tasks$"), show_tasks)],
    states={
        SELECTING_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_selected)],
        AWAITING_PROOF: [
            MessageHandler(filters.PHOTO | filters.Document.ALL | filters.TEXT & ~filters.COMMAND, receive_proof)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^❌ Cancel$"), cancel)],
    allow_reentry=True,
)
