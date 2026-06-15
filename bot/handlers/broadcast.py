import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import database as db
from config import OWNER_ID, ADMIN_IDS

logger = logging.getLogger(__name__)

ADMIN_MENU = ReplyKeyboardMarkup(
    [["➕ Create Task", "📋 List Tasks"], ["📊 Task Stats", "👥 User Stats"],
     ["💸 Withdraw Stats", "💰 Fund Check"], ["📡 Live Report", "🔙 Main Menu"]],
    resize_keyboard=True,
)

BROADCAST_MESSAGE = 40


def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMIN_IDS


async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📢 *Broadcast*\n\nSend a message (text, or photo with caption) to ALL users.\n\nType your message or send a photo now:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return BROADCAST_MESSAGE


async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    users = db.get_all_users()
    sent = 0
    failed = 0

    for u in users:
        if u.get("is_banned"):
            continue
        try:
            if update.message.photo:
                photo = update.message.photo[-1].file_id
                caption = update.message.caption or ""
                await context.bot.send_photo(u["user_id"], photo=photo, caption=caption)
            elif update.message.text:
                await context.bot.send_message(u["user_id"], update.message.text)
            sent += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {u['user_id']}: {e}")
            failed += 1

    await update.message.reply_text(
        f"📢 *Broadcast Complete*\n\n✅ Sent: `{sent}`\n❌ Failed: `{failed}`",
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )
    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
    return ConversationHandler.END


broadcast_conv = ConversationHandler(
    entry_points=[CommandHandler("broadcast", start_broadcast)],
    states={
        BROADCAST_MESSAGE: [
            MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, send_broadcast)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_broadcast), MessageHandler(filters.Regex("^❌ Cancel$"), cancel_broadcast)],
    allow_reentry=True,
)
