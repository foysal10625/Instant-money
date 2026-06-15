import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import database as db
from config import OWNER_ID, ADMIN_IDS

logger = logging.getLogger(__name__)

MAIN_MENU = ReplyKeyboardMarkup(
    [["📋 Tasks", "💰 Balance"], ["👫 Refer", "💸 Withdraw"], ["👤 Profile"]],
    resize_keyboard=True,
)


def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMIN_IDS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    referred_by = None
    if args:
        try:
            referred_by = int(args[0])
            if referred_by == user.id:
                referred_by = None
        except ValueError:
            pass

    existing = db.get_user(user.id)
    if not existing:
        db.create_user(user.id, user.username or user.first_name, referred_by)
        if referred_by and db.get_user(referred_by):
            db.create_referral(referred_by, user.id)
    else:
        if existing.get("is_banned"):
            await update.message.reply_text(
                "🚫 You have been banned from using this bot. Contact support if you think this is a mistake."
            )
            return

    await update.message.reply_text(
        f"👋 Welcome to *Instant Money Bux*, {user.first_name}!\n\n"
        f"Complete tasks, refer friends, and earn real money! 💸\n\n"
        f"Use the menu below to get started:",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    if not u or u.get("is_banned"):
        await update.message.reply_text("🚫 You are banned.")
        return

    main_bal = u.get("balance", 0.0)
    ref_bal = u.get("referral_bonus", 0.0)
    total = main_bal + ref_bal

    await update.message.reply_text(
        f"💰 *Your Balance*\n\n"
        f"Main Balance: `${main_bal:.4f}`\n"
        f"Referral Bonus: `${ref_bal:.4f}`\n"
        f"━━━━━━━━━━━━\n"
        f"Total: `${total:.4f}`",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    if not u or u.get("is_banned"):
        await update.message.reply_text("🚫 You are banned.")
        return

    referrals = db.get_referrals_by_referrer(user.id)
    completed = sum(1 for r in referrals if r.get("task_completed"))
    task_count = db.get_user_task_count(user.id)

    await update.message.reply_text(
        f"👤 *Your Profile*\n\n"
        f"ID: `{user.id}`\n"
        f"Username: @{user.username or 'N/A'}\n"
        f"Balance: `${u.get('balance', 0):.4f}`\n"
        f"Referral Earnings: `${u.get('referral_bonus', 0):.4f}`\n"
        f"Total Referrals: `{len(referrals)}`\n"
        f"Referrals Who Completed Tasks: `{completed}`\n"
        f"Tasks Completed: `{task_count}`\n"
        f"Joined: `{u.get('joined_at', 'N/A')}`",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    if not u or u.get("is_banned"):
        await update.message.reply_text("🚫 You are banned.")
        return

    bot = context.bot
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={user.id}"

    referrals = db.get_referrals_by_referrer(user.id)
    completed = sum(1 for r in referrals if r.get("task_completed"))

    await update.message.reply_text(
        f"👫 *Your Referral Info*\n\n"
        f"Your link:\n`{link}`\n\n"
        f"Total Referrals: `{len(referrals)}`\n"
        f"Completed (earned bonus): `{completed}`\n\n"
        f"You earn *20%* of any task reward when your referred user completes a task! 🎉",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "💰 Balance":
        await cmd_balance(update, context)
    elif text == "👤 Profile":
        await cmd_profile(update, context)
    elif text == "👫 Refer":
        await cmd_refer(update, context)
