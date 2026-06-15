import logging
import csv
import io
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import database as db
import sheets
import config

logger = logging.getLogger(__name__)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["➕ Create Task", "📋 List Tasks"],
        ["📊 Task Stats", "👥 User Stats"],
        ["💸 Withdraw Stats", "💰 Fund Check"],
        ["📡 Live Report", "📥 Download Sheet"],
        ["🔙 Main Menu"],
    ],
    resize_keyboard=True,
)

MAIN_MENU = ReplyKeyboardMarkup(
    [["📋 Tasks", "💰 Balance"], ["👫 Refer", "💸 Withdraw"], ["👤 Profile"]],
    resize_keyboard=True,
)

CREATE_TITLE = 20
CREATE_DESC = 21
CREATE_REWARD = 22
CREATE_TYPE = 23
CREATE_PASS = 24
LIVE_REPORT_FILE = 30
DOWNLOAD_CHOICE = 40
DOWNLOAD_TYPE_CHOICE = 41


def is_owner(user_id: int) -> bool:
    return user_id == config.OWNER_ID


def is_admin(user_id: int) -> bool:
    return user_id == config.OWNER_ID or user_id in config.ADMIN_IDS


# ── Admin Panel ────────────────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    await update.message.reply_text(
        "🛠 *Instant Money Bux — Admin Panel*\n\nChoose an action:",
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )


# ── Ban / Unban ────────────────────────────────────────────────────────────────

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    if target_id == config.OWNER_ID:
        await update.message.reply_text("Cannot ban the owner.")
        return
    db.set_user_banned(target_id, True)
    await update.message.reply_text(f"🚫 User `{target_id}` has been banned.", parse_mode="Markdown")
    try:
        await context.bot.send_message(target_id, "🚫 You have been banned from Instant Money Bux.")
    except Exception:
        pass


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    db.set_user_banned(target_id, False)
    await update.message.reply_text(f"✅ User `{target_id}` has been unbanned.", parse_mode="Markdown")
    try:
        await context.bot.send_message(target_id, "✅ You have been unbanned. Welcome back to Instant Money Bux!")
    except Exception:
        pass


# ── Toggle Tasks ───────────────────────────────────────────────────────────────

async def cmd_toggle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only the owner can toggle the task system.")
        return
    config.TASK_SYSTEM_ENABLED = not config.TASK_SYSTEM_ENABLED
    state = "ENABLED ✅" if config.TASK_SYSTEM_ENABLED else "DISABLED ❌"
    await update.message.reply_text(f"Task system is now *{state}*.", parse_mode="Markdown")


# ── Stats Commands ─────────────────────────────────────────────────────────────

async def cmd_taskstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    stats = db.get_all_task_stats()
    if not stats:
        await update.message.reply_text("No data yet.")
        return
    lines = ["📊 *Task Completion Stats*\n"]
    for s in stats[:30]:
        name = f"@{s['username']}" if s.get("username") else str(s["user_id"])
        lines.append(f"{name}: `{s['completed']}` tasks")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_userstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    users = db.get_all_users()
    if not users:
        await update.message.reply_text("No users found.")
        return
    lines = ["👥 *User Stats*\n"]
    for u in users[:20]:
        name = f"@{u['username']}" if u.get("username") else str(u["user_id"])
        tasks = db.get_user_task_count(u["user_id"])
        refs = db.get_referrals_by_referrer(u["user_id"])
        wds = db.get_user_withdrawals(u["user_id"])
        total_bal = u.get("balance", 0) + u.get("referral_bonus", 0)
        lines.append(f"{name}: bal=`${total_bal:.4f}` refs=`{len(refs)}` tasks=`{tasks}` wds=`{len(wds)}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_withdrawstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    all_w = db.get_all_withdraw_stats()
    pending = [w for w in all_w if w["status"] == "pending"]
    approved = [w for w in all_w if w["status"] == "approved"]
    rejected = [w for w in all_w if w["status"] == "rejected"]
    await update.message.reply_text(
        f"💸 *Withdrawal Stats*\n\n"
        f"Pending: `{len(pending)}` (${sum(w['amount'] for w in pending):.4f})\n"
        f"Approved: `{len(approved)}` (${sum(w['amount'] for w in approved):.4f})\n"
        f"Rejected: `{len(rejected)}` (${sum(w['amount'] for w in rejected):.4f})",
        parse_mode="Markdown",
    )


async def cmd_fundcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    all_w = db.get_all_withdraw_stats()
    pending_total = sum(w["amount"] for w in all_w if w["status"] == "pending")
    all_users = db.get_all_users()
    total_balances = sum(u.get("balance", 0) + u.get("referral_bonus", 0) for u in all_users)
    approved_total = sum(w["amount"] for w in all_w if w["status"] == "approved")
    await update.message.reply_text(
        f"💰 *Fund Check*\n\n"
        f"Total user balances: `${total_balances:.4f}`\n"
        f"Pending withdrawals: `${pending_total:.4f}`\n"
        f"Total paid out: `${approved_total:.4f}`\n\n"
        f"{'✅ Sufficient funds.' if total_balances >= pending_total else '⚠️ Insufficient funds for pending withdrawals!'}",
        parse_mode="Markdown",
    )


async def cmd_fakerefer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    users = db.get_all_users()
    lines = ["🚫 *Fake Referral Report*\n"]
    for u in users:
        referrals = db.get_referrals_by_referrer(u["user_id"])
        if not referrals:
            continue
        completed = sum(1 for r in referrals if r.get("task_completed"))
        if len(referrals) > 3 and completed == 0:
            name = f"@{u['username']}" if u.get("username") else str(u["user_id"])
            lines.append(f"⚠️ {name} (`{u['user_id']}`): {len(referrals)} refs, {completed} completed — SUSPICIOUS")
    if len(lines) == 1:
        await update.message.reply_text("✅ No suspicious fake referral activity detected.")
    else:
        await update.message.reply_text("\n".join(lines[:30]), parse_mode="Markdown")


# ── List / Delete Tasks ────────────────────────────────────────────────────────

async def cmd_list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    tasks = db.get_active_tasks()
    if not tasks:
        await update.message.reply_text("No active tasks.", reply_markup=ADMIN_MENU)
        return
    lines = ["📋 *Active Tasks*\n"]
    for t in tasks:
        ttype = t.get("task_type", "instagram").capitalize()
        lines.append(f"ID `{t['task_id']}`: *{t['title']}* [{ttype}] — `${t['reward']:.4f}` | pw: `{t.get('task_password','')}`")
    lines.append("\nUse /deltask <task_id> to remove.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=ADMIN_MENU)


async def cmd_deltask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /deltask <task_id>")
        return
    try:
        task_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Invalid task ID.")
        return
    db.delete_task(task_id)
    await update.message.reply_text(f"✅ Task `{task_id}` deactivated.", parse_mode="Markdown")


# ── Create Task Conversation ───────────────────────────────────────────────────

async def start_create_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END
    await update.message.reply_text(
        "➕ *Create New Task*\n\nStep 1 of 5: Enter the task *title*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return CREATE_TITLE


async def receive_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END
    context.user_data["new_task_title"] = update.message.text.strip()
    await update.message.reply_text("Step 2 of 5: Enter the task *description*:", parse_mode="Markdown")
    return CREATE_DESC


async def receive_task_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END
    context.user_data["new_task_desc"] = update.message.text.strip()
    await update.message.reply_text("Step 3 of 5: Enter the *reward* amount (e.g. 0.05):", parse_mode="Markdown")
    return CREATE_REWARD


async def receive_task_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END
    try:
        reward = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Please enter a valid number (e.g. 0.05).")
        return CREATE_REWARD
    context.user_data["new_task_reward"] = reward
    await update.message.reply_text(
        "Step 4 of 5: Select the *platform* for this task:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["📸 Instagram", "📘 Facebook"], ["❌ Cancel"]], resize_keyboard=True),
    )
    return CREATE_TYPE


async def receive_task_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END
    text = update.message.text
    if "Instagram" in text:
        task_type = "instagram"
    elif "Facebook" in text:
        task_type = "facebook"
    else:
        await update.message.reply_text("Please choose Instagram or Facebook.")
        return CREATE_TYPE
    context.user_data["new_task_type"] = task_type
    await update.message.reply_text(
        "Step 5 of 5: Enter the *password* users must use to create the account:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return CREATE_PASS


async def receive_task_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END
    task_password = update.message.text.strip()
    title = context.user_data["new_task_title"]
    desc = context.user_data["new_task_desc"]
    reward = context.user_data["new_task_reward"]
    task_type = context.user_data["new_task_type"]
    task_id = db.create_task(title, desc, reward, update.effective_user.id, task_type, task_password)
    platform = "Instagram" if task_type == "instagram" else "Facebook"
    await update.message.reply_text(
        f"✅ *Task Created!*\n\n"
        f"ID: `{task_id}`\n"
        f"Title: *{title}*\n"
        f"Platform: {platform}\n"
        f"Password: `{task_password}`\n"
        f"Reward: `${reward:.4f}`",
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )
    return ConversationHandler.END


# ── Download Sheet Conversation ────────────────────────────────────────────────

async def start_download_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📥 *Download Sheet*\n\nWhich platform data do you want?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["📸 Instagram", "📘 Facebook"], ["📊 All Platforms"], ["❌ Cancel"]],
            resize_keyboard=True,
        ),
    )
    return DOWNLOAD_CHOICE


async def receive_download_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    if "Instagram" in text:
        context.user_data["dl_platform"] = "instagram"
    elif "Facebook" in text:
        context.user_data["dl_platform"] = "facebook"
    elif "All" in text:
        context.user_data["dl_platform"] = None
    else:
        await update.message.reply_text("Please choose from the buttons.")
        return DOWNLOAD_CHOICE

    await update.message.reply_text(
        "Which sheet format do you want?",
        reply_markup=ReplyKeyboardMarkup(
            [["📄 Full Sheet", "🔑 Credentials Only"], ["❌ Cancel"]],
            resize_keyboard=True,
        ),
    )
    return DOWNLOAD_TYPE_CHOICE


async def receive_download_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    platform = context.user_data.get("dl_platform")

    if "Full" in text:
        sheet_type = "full"
    elif "Credentials" in text:
        sheet_type = "creds"
    else:
        await update.message.reply_text("Please choose from the buttons.")
        return DOWNLOAD_TYPE_CHOICE

    await update.message.reply_text("⏳ Generating sheet...", reply_markup=ADMIN_MENU)

    subs = db.get_approved_submissions(task_type=platform)

    output = io.StringIO()
    writer = csv.writer(output)

    platform_label = platform.capitalize() if platform else "All"

    if sheet_type == "full":
        writer.writerow([
            "Sub ID", "User ID", "TG Username", "Task", "Platform",
            "Acc Username", "Password", "2FA Key", "Reward ($)", "Date"
        ])
        for s in subs:
            writer.writerow([
                s.get("submission_id", ""),
                s.get("user_id", ""),
                s.get("tg_username", ""),
                s.get("title", ""),
                s.get("task_type", "").capitalize(),
                s.get("acc_username", ""),
                s.get("acc_password", ""),
                s.get("twofa_key", ""),
                f"{s.get('reward', 0):.4f}",
                s.get("submitted_at", ""),
            ])
        filename = f"imb_full_{platform_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        caption = f"📄 *Full Sheet — {platform_label}*\nTotal records: `{len(subs)}`"
    else:
        writer.writerow(["Acc Username", "Password", "2FA Key"])
        for s in subs:
            writer.writerow([
                s.get("acc_username", ""),
                s.get("acc_password", ""),
                s.get("twofa_key", ""),
            ])
        filename = f"imb_credentials_{platform_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        caption = f"🔑 *Credentials Sheet — {platform_label}*\nTotal records: `{len(subs)}`"

    output.seek(0)
    csv_bytes = output.getvalue().encode("utf-8")

    await update.message.reply_document(
        document=InputFile(io.BytesIO(csv_bytes), filename=filename),
        caption=caption,
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )
    return ConversationHandler.END


# ── Live ID Report Conversation ────────────────────────────────────────────────

async def start_livereport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📡 *Live ID Report*\n\n"
        "Upload a file (CSV, XLSX, or TXT) containing confirmed live account usernames / UIDs.\n\n"
        "The bot will match them against submitted account usernames and add the task reward to each matched user's balance.\n\n"
        "💡 *Tip:* Use *📥 Download Sheet → Credentials Only* to see all submitted usernames.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return LIVE_REPORT_FILE


async def receive_livereport_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    live_ids = set()

    if update.message.document:
        file = await update.message.document.get_file()
        file_bytes = await file.download_as_bytearray()
        content = file_bytes.decode("utf-8", errors="ignore")

        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell:
                        live_ids.add(str(cell).strip())
        except Exception:
            reader = csv.reader(io.StringIO(content))
            for row in reader:
                for cell in row:
                    cell = cell.strip()
                    if cell:
                        live_ids.add(cell)
            if not live_ids:
                for line in content.splitlines():
                    line = line.strip()
                    if line:
                        live_ids.add(line)

    elif update.message.text:
        for line in update.message.text.splitlines():
            for part in line.split(","):
                part = part.strip()
                if part:
                    live_ids.add(part)

    if not live_ids:
        await update.message.reply_text("❌ No IDs found. Try again.")
        return LIVE_REPORT_FILE

    all_acc_usernames = db.get_approved_acc_usernames()

    matched_users = {}   # user_id → {username, subs: [{submission_id, reward}]}
    for live_id in live_ids:
        if live_id in all_acc_usernames:
            subs = db.get_submissions_by_acc_username(live_id)
            for s in subs:
                uid = s["user_id"]
                if uid not in matched_users:
                    matched_users[uid] = {"tg_username": s["tg_username"], "reward": 0.0, "ids": []}
                matched_users[uid]["reward"] += s["reward"]
                matched_users[uid]["ids"].append(live_id)

    total_bonus = 0.0
    for user_id, info in matched_users.items():
        reward = info["reward"]
        db.update_user_balance(user_id, reward, "balance")
        db.add_transaction(user_id, "live_id_bonus", reward, "Live ID match — balance added")
        total_bonus += reward
        for lid in info["ids"]:
            db.add_live_id_match(user_id, lid, reward)
        try:
            await context.bot.send_message(
                user_id,
                f"🎉 Your account was verified as live!\n"
                f"💰 `${reward:.4f}` has been added to your balance.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    total_matched_ids = sum(len(info["ids"]) for info in matched_users.values())
    summary = [
        "📡 *Live ID Report Summary*\n",
        f"IDs uploaded: `{len(live_ids)}`",
        f"Matched IDs: `{total_matched_ids}`",
        f"Matched users: `{len(matched_users)}`",
        f"Total balance added: `${total_bonus:.4f}`",
        f"Unmatched IDs: `{len(live_ids) - total_matched_ids}`",
    ]
    if matched_users:
        summary.append("\n*Matched Users:*")
        for uid, info in list(matched_users.items())[:20]:
            name = f"@{info['tg_username']}" if info.get("tg_username") else str(uid)
            summary.append(f"{name}: `{len(info['ids'])}` ID(s) → `${info['reward']:.4f}`")

    await update.message.reply_text("\n".join(summary), parse_mode="Markdown", reply_markup=ADMIN_MENU)
    return ConversationHandler.END


async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
    return ConversationHandler.END


# ── Conversation Handlers ──────────────────────────────────────────────────────

create_task_conv = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^➕ Create Task$"), start_create_task),
        CommandHandler("createtask", start_create_task),
    ],
    states={
        CREATE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_title)],
        CREATE_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_desc)],
        CREATE_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_reward)],
        CREATE_TYPE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_type)],
        CREATE_PASS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_password)],
    },
    fallbacks=[CommandHandler("cancel", cancel_admin), MessageHandler(filters.Regex("^❌ Cancel$"), cancel_admin)],
    allow_reentry=True,
)

download_sheet_conv = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^📥 Download Sheet$"), start_download_sheet),
        CommandHandler("downloadsheet", start_download_sheet),
    ],
    states={
        DOWNLOAD_CHOICE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_download_platform)],
        DOWNLOAD_TYPE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_download_type)],
    },
    fallbacks=[CommandHandler("cancel", cancel_admin), MessageHandler(filters.Regex("^❌ Cancel$"), cancel_admin)],
    allow_reentry=True,
)

livereport_conv = ConversationHandler(
    entry_points=[
        CommandHandler("livereport", start_livereport),
        MessageHandler(filters.Regex("^📡 Live Report$"), start_livereport),
    ],
    states={
        LIVE_REPORT_FILE: [
            MessageHandler(filters.Document.ALL | filters.TEXT & ~filters.COMMAND, receive_livereport_file)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_admin), MessageHandler(filters.Regex("^❌ Cancel$"), cancel_admin)],
    allow_reentry=True,
)
