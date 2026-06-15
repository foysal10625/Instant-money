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
        ["🗑 Delete Task", "📊 Task Stats"],
        ["👥 User Stats", "💸 Withdraw Stats"],
        ["💰 Fund Check", "📡 Live Report"],
        ["📥 Download Sheet", "🔄 Balance Reset"],
        ["💵 Set Min Withdraw", "🔛 Toggle Withdraw"],
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
DELETE_TASK_SELECT = 50
BALRESET_USERID = 60
SET_MIN_WITHDRAW = 70


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


# ── Toggle Withdraw ────────────────────────────────────────────────────────────

async def cmd_toggle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    config.WITHDRAW_SYSTEM_ENABLED = not config.WITHDRAW_SYSTEM_ENABLED
    state = "ENABLED ✅" if config.WITHDRAW_SYSTEM_ENABLED else "DISABLED ❌"
    await update.message.reply_text(f"Withdrawal system is now *{state}*.", parse_mode="Markdown")


# ── Set Min Withdraw ───────────────────────────────────────────────────────────

async def start_set_min_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END
    await update.message.reply_text(
        f"💵 *Set Minimum Withdrawal*\n\n"
        f"Current minimum: `${config.MIN_WITHDRAW:.2f}`\n\n"
        f"Enter the new minimum withdrawal amount:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return SET_MIN_WITHDRAW


async def receive_min_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END
    try:
        new_min = float(update.message.text.strip())
        if new_min < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid positive number (e.g. 2.00).")
        return SET_MIN_WITHDRAW
    config.MIN_WITHDRAW = new_min
    await update.message.reply_text(
        f"✅ Minimum withdrawal set to `${new_min:.2f}`.",
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )
    return ConversationHandler.END


# ── Balance Reset ──────────────────────────────────────────────────────────────

async def start_balreset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔄 *Balance Reset*\n\nEnter the *User ID* of the user whose balance you want to reset to $0.00:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return BALRESET_USERID


async def receive_balreset_userid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    try:
        target_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Invalid User ID. Please enter a number.")
        return BALRESET_USERID

    u = db.get_user(target_id)
    if not u:
        await update.message.reply_text(
            f"❌ No user found with ID `{target_id}`.",
            parse_mode="Markdown",
        )
        return BALRESET_USERID

    old_bal = u.get("balance", 0) + u.get("referral_bonus", 0)
    db.reset_user_balance(target_id)
    db.add_transaction(target_id, "balance_reset", -old_bal, f"Balance reset by admin {update.effective_user.id}")

    name = f"@{u['username']}" if u.get("username") else str(target_id)
    await update.message.reply_text(
        f"✅ *Balance Reset*\n\n"
        f"User: {name} (`{target_id}`)\n"
        f"Previous balance: `${old_bal:.4f}`\n"
        f"New balance: `$0.0000`",
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )

    try:
        await context.bot.send_message(
            target_id,
            "⚠️ Your balance has been reset to $0.00 by an admin.",
        )
    except Exception:
        pass

    return ConversationHandler.END


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
        f"Withdraw system: {'✅ ON' if config.WITHDRAW_SYSTEM_ENABLED else '❌ OFF'}\n"
        f"Minimum: `${config.MIN_WITHDRAW:.2f}`\n\n"
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
            "Acc Username / UID", "Password", "2FA Key", "Reward ($)", "Date"
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
        # Facebook credentials: UID - Password - 2FA
        # Instagram credentials: Username - Password - 2FA
        if platform == "facebook":
            writer.writerow(["UID", "Password", "2FA Key"])
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
        "The bot will match them against submitted accounts, add the reward to each matched user's balance "
        "*one by one*, and send each user a notification per matched account.\n\n"
        "💡 Already-credited IDs will be automatically skipped.",
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

    total_credited = 0
    total_skipped = 0
    total_unmatched = 0
    total_bonus = 0.0
    matched_summary = {}  # user_id → count of live IDs credited

    for live_id in live_ids:
        if live_id not in all_acc_usernames:
            total_unmatched += 1
            continue

        subs = db.get_submissions_by_acc_username(live_id)
        for s in subs:
            uid = s["user_id"]

            # Skip if this exact live ID was already credited to this user
            if db.has_live_id_match(uid, live_id):
                total_skipped += 1
                continue

            reward = s["reward"]

            # Add balance and record the match
            db.update_user_balance(uid, reward, "balance")
            db.add_transaction(uid, "live_id_bonus", reward, f"Live ID match: {live_id}")
            db.add_live_id_match(uid, live_id, reward)
            total_bonus += reward
            total_credited += 1

            if uid not in matched_summary:
                matched_summary[uid] = {"tg_username": s["tg_username"], "count": 0, "total": 0.0}
            matched_summary[uid]["count"] += 1
            matched_summary[uid]["total"] += reward

            # Send individual notification per live account
            try:
                await context.bot.send_message(
                    uid,
                    f"🎉 *Account Verified as Live!*\n\n"
                    f"Account: `{live_id}`\n"
                    f"💰 `${reward:.4f}` has been added to your balance.\n\n"
                    f"Check /balance to see your updated balance.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    summary = [
        "📡 *Live ID Report Summary*\n",
        f"IDs uploaded: `{len(live_ids)}`",
        f"Newly credited: `{total_credited}`",
        f"Already credited (skipped): `{total_skipped}`",
        f"Unmatched: `{total_unmatched}`",
        f"Total balance added: `${total_bonus:.4f}`",
        f"Users notified: `{len(matched_summary)}`",
    ]
    if matched_summary:
        summary.append("\n*Credited Users:*")
        for uid, info in list(matched_summary.items())[:20]:
            name = f"@{info['tg_username']}" if info.get("tg_username") else str(uid)
            summary.append(f"{name}: `{info['count']}` account(s) → `${info['total']:.4f}`")

    await update.message.reply_text("\n".join(summary), parse_mode="Markdown", reply_markup=ADMIN_MENU)
    return ConversationHandler.END


async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
    return ConversationHandler.END


# ── Delete Task Conversation ───────────────────────────────────────────────────

async def start_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END

    tasks = db.get_active_tasks()
    if not tasks:
        await update.message.reply_text("No active tasks to delete.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    context.user_data["delete_tasks_map"] = {}
    buttons = []
    for t in tasks:
        ttype = "📸" if t.get("task_type") == "instagram" else "📘"
        label = f"{ttype} {t['title']} (${t['reward']:.4f})"
        context.user_data["delete_tasks_map"][label] = t
        buttons.append([label])
    buttons.append(["❌ Cancel"])

    await update.message.reply_text(
        "🗑 *Delete Task*\n\nSelect the task you want to delete:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True),
    )
    return DELETE_TASK_SELECT


async def confirm_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    tasks_map = context.user_data.get("delete_tasks_map", {})
    task = tasks_map.get(text)

    if not task:
        await update.message.reply_text("Please select a task from the list.")
        return DELETE_TASK_SELECT

    db.delete_task(task["task_id"])

    platform = "Instagram" if task.get("task_type") == "instagram" else "Facebook"
    await update.message.reply_text(
        f"✅ *Task Deleted*\n\n"
        f"Title: *{task['title']}*\n"
        f"Platform: {platform}\n"
        f"Reward: `${task['reward']:.4f}`\n\n"
        f"The task has been removed and users can no longer select it.",
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )
    return ConversationHandler.END


# ── Conversation Handlers ──────────────────────────────────────────────────────

create_task_conv = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^➕ Create Task$"), start_create_task),
        CommandHandler("createtask", start_create_task),
    ],
    states={
        CREATE_TITLE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_title)],
        CREATE_DESC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_desc)],
        CREATE_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_reward)],
        CREATE_TYPE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_type)],
        CREATE_PASS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_password)],
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

delete_task_conv = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^🗑 Delete Task$"), start_delete_task),
        CommandHandler("deletetask", start_delete_task),
    ],
    states={
        DELETE_TASK_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_task)],
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

balreset_conv = ConversationHandler(
    entry_points=[
        CommandHandler("balreset", start_balreset),
        MessageHandler(filters.Regex("^🔄 Balance Reset$"), start_balreset),
    ],
    states={
        BALRESET_USERID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_balreset_userid)],
    },
    fallbacks=[CommandHandler("cancel", cancel_admin), MessageHandler(filters.Regex("^❌ Cancel$"), cancel_admin)],
    allow_reentry=True,
)

set_min_withdraw_conv = ConversationHandler(
    entry_points=[
        CommandHandler("setminwithdraw", start_set_min_withdraw),
        MessageHandler(filters.Regex("^💵 Set Min Withdraw$"), start_set_min_withdraw),
    ],
    states={
        SET_MIN_WITHDRAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_min_withdraw)],
    },
    fallbacks=[CommandHandler("cancel", cancel_admin), MessageHandler(filters.Regex("^❌ Cancel$"), cancel_admin)],
    allow_reentry=True,
)
