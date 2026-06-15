import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

import database as db
from config import BOT_TOKEN, OWNER_ID
from handlers.user import cmd_start, cmd_balance, cmd_profile, cmd_refer, handle_menu_text
from handlers.tasks import task_conv_handler
from handlers.withdraw import withdraw_conv_handler, handle_withdrawal_callback
from handlers.broadcast import broadcast_conv
from handlers.admin import (
    cmd_admin, cmd_ban, cmd_unban, cmd_toggle_tasks,
    cmd_taskstats, cmd_userstats, cmd_withdrawstats, cmd_fundcheck,
    cmd_fakerefer, cmd_list_tasks, cmd_deltask, cmd_downloadsheet,
    create_task_conv, livereport_conv,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAIN_MENU = ReplyKeyboardMarkup(
    [["📋 Tasks", "💰 Balance"], ["👫 Refer", "💸 Withdraw"], ["👤 Profile"]],
    resize_keyboard=True,
)


def is_admin(user_id: int) -> bool:
    from config import ADMIN_IDS
    return user_id == OWNER_ID or user_id in ADMIN_IDS


async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📋 List Tasks":
        await cmd_list_tasks(update, context)
    elif text == "📊 Task Stats":
        await cmd_taskstats(update, context)
    elif text == "👥 User Stats":
        await cmd_userstats(update, context)
    elif text == "💸 Withdraw Stats":
        await cmd_withdrawstats(update, context)
    elif text == "💰 Fund Check":
        await cmd_fundcheck(update, context)
    elif text == "📥 Download Sheet":
        await cmd_downloadsheet(update, context)
    elif text == "🔙 Main Menu":
        await update.message.reply_text("Back to main menu.", reply_markup=MAIN_MENU)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        msg = (
            "🛠 *Instant Money Bux — Admin Commands*\n\n"
            "/admin — Open admin panel\n"
            "/createtask — Create a new task\n"
            "/deltask <id> — Delete a task\n"
            "/downloadsheet — Download all task submissions as CSV\n"
            "/ban <user_id> — Ban a user\n"
            "/unban <user_id> — Unban a user\n"
            "/taskstats — Task completion stats\n"
            "/userstats — User stats\n"
            "/withdrawstats — Withdrawal stats\n"
            "/fundcheck — Check funds\n"
            "/fakerefer — Fake referral report\n"
            "/livereport — Live ID matching\n"
            "/broadcast — Broadcast to all users\n"
            "/toggletasks — Toggle task system (owner only)\n"
        )
    else:
        msg = (
            "💸 *Instant Money Bux*\n\n"
            "/start — Return to main menu\n"
            "/balance — Check your balance\n"
            "/refer — Get your referral link\n"
            "/withdraw — Request a withdrawal\n"
            "/profile — View your profile\n"
            "/help — Show this help\n"
        )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Please set it in Replit Secrets.")
        sys.exit(1)

    db.init_db()
    logger.info("Database initialized.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("refer", cmd_refer))

    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("toggletasks", cmd_toggle_tasks))
    app.add_handler(CommandHandler("taskstats", cmd_taskstats))
    app.add_handler(CommandHandler("userstats", cmd_userstats))
    app.add_handler(CommandHandler("withdrawstats", cmd_withdrawstats))
    app.add_handler(CommandHandler("fundcheck", cmd_fundcheck))
    app.add_handler(CommandHandler("fakerefer", cmd_fakerefer))
    app.add_handler(CommandHandler("deltask", cmd_deltask))
    app.add_handler(CommandHandler("downloadsheet", cmd_downloadsheet))

    app.add_handler(create_task_conv)
    app.add_handler(livereport_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(task_conv_handler)
    app.add_handler(withdraw_conv_handler)

    app.add_handler(CallbackQueryHandler(handle_withdrawal_callback, pattern=r"^w(approve|reject)_\d+$"))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(
            "^(📋 List Tasks|📊 Task Stats|👥 User Stats|💸 Withdraw Stats|💰 Fund Check|🔙 Main Menu|📡 Live Report|📥 Download Sheet)$"
        ),
        handle_admin_menu,
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex("^(💰 Balance|👤 Profile|👫 Refer)$"),
        handle_menu_text,
    ))

    app.add_error_handler(error_handler)

    logger.info("Instant Money Bux bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
