import logging
import config as config_module
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import database as db
from config import OWNER_ID, ADMIN_IDS, WITHDRAW_METHODS

logger = logging.getLogger(__name__)

AMOUNT = 1
METHOD = 2
DETAILS = 3

MAIN_MENU = ReplyKeyboardMarkup(
    [["📋 Tasks", "💰 Balance"], ["👫 Refer", "💸 Withdraw"], ["👤 Profile"]],
    resize_keyboard=True,
)


def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMIN_IDS


async def start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    if not u or u.get("is_banned"):
        await update.message.reply_text("🚫 You are banned.")
        return ConversationHandler.END

    if not config_module.WITHDRAW_SYSTEM_ENABLED:
        await update.message.reply_text(
            "❌ Withdrawals are currently disabled. Please check back later.",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    min_withdraw = config_module.MIN_WITHDRAW
    total = u.get("balance", 0) + u.get("referral_bonus", 0)
    if total < min_withdraw:
        await update.message.reply_text(
            f"❌ Minimum withdrawal is `${min_withdraw:.2f}`.\nYour balance: `${total:.4f}`",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"💸 *Withdraw*\n\nYour balance: `${total:.4f}`\nMinimum: `${min_withdraw:.2f}`\n\nHow much would you like to withdraw?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return AMOUNT


async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    user = update.effective_user
    u = db.get_user(user.id)
    total = u.get("balance", 0) + u.get("referral_bonus", 0)
    min_withdraw = config_module.MIN_WITHDRAW

    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return AMOUNT

    if amount < min_withdraw:
        await update.message.reply_text(f"❌ Minimum is ${min_withdraw:.2f}. Try again.")
        return AMOUNT

    if amount > total:
        await update.message.reply_text(f"❌ You only have ${total:.4f}. Try again.")
        return AMOUNT

    context.user_data["withdraw_amount"] = amount
    method_buttons = [[m] for m in WITHDRAW_METHODS] + [["❌ Cancel"]]
    await update.message.reply_text(
        "Select your payment method:",
        reply_markup=ReplyKeyboardMarkup(method_buttons, resize_keyboard=True),
    )
    return METHOD


async def receive_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    method = update.message.text.strip()
    if method not in WITHDRAW_METHODS:
        await update.message.reply_text("Please select a valid method from the buttons.")
        return METHOD

    context.user_data["withdraw_method"] = method
    await update.message.reply_text(
        f"Enter your {method} account details (address/number):",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return DETAILS


async def receive_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    user = update.effective_user
    u = db.get_user(user.id)
    amount = context.user_data.get("withdraw_amount")
    method = context.user_data.get("withdraw_method")
    details = update.message.text.strip()

    total = u.get("balance", 0) + u.get("referral_bonus", 0)
    if amount > total:
        await update.message.reply_text("❌ Insufficient balance.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    main_bal = u.get("balance", 0)
    ref_bal = u.get("referral_bonus", 0)
    deduct_main = min(amount, main_bal)
    deduct_ref = amount - deduct_main
    if deduct_main > 0:
        db.update_user_balance(user.id, -deduct_main, "balance")
    if deduct_ref > 0:
        db.update_user_balance(user.id, -deduct_ref, "referral_bonus")

    wid = db.create_withdrawal(user.id, amount, method, details)
    db.add_transaction(user.id, "withdrawal", -amount, f"Withdraw via {method}")

    username = f"@{user.username}" if user.username else user.first_name
    notif = (
        f"💸 *New Withdrawal Request*\n\n"
        f"User: {username} (`{user.id}`)\n"
        f"Amount: `${amount:.4f}`\n"
        f"Method: {method}\n"
        f"Details: `{details}`\n"
        f"Withdrawal ID: `{wid}`"
    )

    approve_btn = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"wapprove_{wid}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"wreject_{wid}"),
        ]
    ])

    admins = [OWNER_ID] + ADMIN_IDS
    for admin_id in set(admins):
        try:
            await context.bot.send_message(admin_id, notif, parse_mode="Markdown", reply_markup=approve_btn)
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")

    await update.message.reply_text(
        f"✅ Withdrawal request submitted!\n\nAmount: `${amount:.4f}`\nMethod: {method}\nID: `{wid}`\n\nYou will be notified once processed.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def handle_withdrawal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.answer("Not authorized.", show_alert=True)
        return

    data = query.data
    if data.startswith("wapprove_"):
        wid = int(data.split("_")[1])
        action = "approve"
    elif data.startswith("wreject_"):
        wid = int(data.split("_")[1])
        action = "reject"
    else:
        return

    w = db.get_withdrawal(wid)
    if not w:
        await query.edit_message_text("❌ Withdrawal not found.")
        return

    if w["status"] != "pending":
        await query.answer(f"Already {w['status']}.", show_alert=True)
        return

    if action == "approve":
        db.update_withdrawal_status(wid, "approved", admin_id)
        try:
            await context.bot.send_message(
                w["user_id"],
                f"✅ Your withdrawal of `${w['amount']:.4f}` via {w['payment_method']} has been *approved*!",
                parse_mode="Markdown",
            )
        except Exception:
            pass
        new_text = query.message.text + f"\n\n✅ *Approved* by admin `{admin_id}`"
        await query.edit_message_text(new_text, parse_mode="Markdown")

    else:
        db.update_withdrawal_status(wid, "rejected", admin_id)
        db.update_user_balance(w["user_id"], w["amount"], "balance")
        db.add_transaction(w["user_id"], "withdrawal_refund", w["amount"], "Withdrawal rejected - refunded")
        try:
            await context.bot.send_message(
                w["user_id"],
                f"❌ Your withdrawal of `${w['amount']:.4f}` was *rejected*. Your balance has been refunded.",
                parse_mode="Markdown",
            )
        except Exception:
            pass
        new_text = query.message.text + f"\n\n❌ *Rejected* by admin `{admin_id}`"
        await query.edit_message_text(new_text, parse_mode="Markdown")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


withdraw_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^💸 Withdraw$"), start_withdraw)],
    states={
        AMOUNT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
        METHOD:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_method)],
        DETAILS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_details)],
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^❌ Cancel$"), cancel)],
    allow_reentry=True,
)
