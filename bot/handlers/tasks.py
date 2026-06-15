import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import database as db
import sheets
from config import OWNER_ID, ADMIN_IDS, TASK_SYSTEM_ENABLED, REFERRAL_BONUS_PERCENT

logger = logging.getLogger(__name__)

SELECTING_TASK = 1
AWAITING_PROOF = 2

CREATE_TITLE = 10
CREATE_DESC = 11
CREATE_REWARD = 12

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
            "⚠️ The task system is currently disabled by the owner.",
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
        "📋 *Available Tasks*\n\nSelect a task to begin:",
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
        f"📸 Please submit your proof (screenshot or ID). Send it as an image or paste text/ID:",
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

    admins_to_notify = [OWNER_ID] + ADMIN_IDS

    username = f"@{user.username}" if user.username else user.first_name
    caption = (
        f"📬 *New Task Submission*\n\n"
        f"User: {username} (`{user.id}`)\n"
        f"Task: *{task['title']}*\n"
        f"Reward: `${task['reward']:.4f}`\n"
        f"Proof Type: {proof_type}\n"
        f"Submission ID: `{sub_id}`"
    )

    approve_btn = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{sub_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{sub_id}"),
        ]
    ])

    bot = context.bot
    for admin_id in set(admins_to_notify):
        try:
            if proof_type == "photo":
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=proof,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=approve_btn,
                )
            elif proof_type == "document":
                await bot.send_document(
                    chat_id=admin_id,
                    document=proof,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=approve_btn,
                )
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text=caption + f"\n\nProof: `{proof}`",
                    parse_mode="Markdown",
                    reply_markup=approve_btn,
                )
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")

    await update.message.reply_text(
        "✅ Your proof has been submitted! Admins will review it shortly.",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def handle_submission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.answer("Not authorized.", show_alert=True)
        return

    data = query.data
    if data.startswith("approve_"):
        sub_id = int(data.split("_")[1])
        action = "approve"
    elif data.startswith("reject_"):
        sub_id = int(data.split("_")[1])
        action = "reject"
    else:
        return

    sub = db.get_submission(sub_id)
    if not sub:
        await query.edit_message_caption(caption="❌ Submission not found.")
        return

    if sub["status"] != "pending":
        await query.answer(f"Already {sub['status']}.", show_alert=True)
        return

    task = db.get_task(sub["task_id"])
    user = db.get_user(sub["user_id"])

    if action == "approve":
        db.update_submission_status(sub_id, "approved", admin_id)
        reward = task["reward"]
        db.update_user_balance(sub["user_id"], reward, "balance")
        db.add_transaction(sub["user_id"], "task_reward", reward, f"Task: {task['title']}")

        referral = db.get_referral_by_referred(sub["user_id"])
        if referral and not referral.get("task_completed"):
            bonus = round(reward * REFERRAL_BONUS_PERCENT / 100, 6)
            db.update_user_balance(referral["referrer_id"], bonus, "referral_bonus")
            db.mark_referral_completed(sub["user_id"], bonus)
            db.add_transaction(referral["referrer_id"], "referral_bonus", bonus, f"Referral bonus for {sub['user_id']}")
            try:
                await context.bot.send_message(
                    referral["referrer_id"],
                    f"🎉 Your referred user completed a task! You earned `${bonus:.4f}` referral bonus.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        try:
            logged = sheets.log_approved_task(
                sub["user_id"],
                user.get("username", ""),
                task["title"],
                reward,
            )
            if logged:
                db.mark_submission_logged(sub_id)
        except Exception as e:
            logger.warning(f"Sheet logging failed: {e}")

        try:
            await context.bot.send_message(
                sub["user_id"],
                f"✅ Your submission for *{task['title']}* was approved!\n💰 `${reward:.4f}` added to your balance.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

        new_caption = query.message.caption or query.message.text or ""
        new_caption += f"\n\n✅ *Approved* by admin `{admin_id}`"
        try:
            if query.message.caption is not None:
                await query.edit_message_caption(caption=new_caption, parse_mode="Markdown")
            else:
                await query.edit_message_text(text=new_caption, parse_mode="Markdown")
        except Exception:
            pass

    else:
        db.update_submission_status(sub_id, "rejected", admin_id)
        try:
            await context.bot.send_message(
                sub["user_id"],
                f"❌ Your submission for *{task['title']}* was rejected. Please try again with valid proof.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

        new_caption = query.message.caption or query.message.text or ""
        new_caption += f"\n\n❌ *Rejected* by admin `{admin_id}`"
        try:
            if query.message.caption is not None:
                await query.edit_message_caption(caption=new_caption, parse_mode="Markdown")
            else:
                await query.edit_message_text(text=new_caption, parse_mode="Markdown")
        except Exception:
            pass


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
