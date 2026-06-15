import logging
import csv
import io
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import database as db
import sheets
import config

logger = logging.getLogger(__name__)

ADMIN_MENU = ReplyKeyboardMarkup(
    [["➕ Create Task", "📋 List Tasks"], ["📊 Task Stats", "👥 User Stats"],
     ["💸 Withdraw Stats", "💰 Fund Check"], ["📡 Live Report", "📥 Download Sheet"],
     ["🔙 Main Menu"]],
    resize_keyboard=True,
)

MAIN_MENU = ReplyKeyboardMarkup(
    [["📋 Tasks", "💰 Balance"], ["👫 Refer", "💸 Withdraw"], ["👤 Profile"]],
    resize_keyboard=True,
)

CREATE_TITLE = 20
CREATE_DESC = 21
CREATE_REWARD = 22
LIVE_REPORT_FILE = 30


def is_owner(user_id: int) -> bool:
    return user_id == config.OWNER_ID


def is_admin(user_id: int) -> bool:
    return user_id == config.OWNER_ID or user_id in config.ADMIN_IDS


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    await update.message.reply_text(
        "🛠 *Instant Money Bux — Admin Panel*\n\nChoose an action:",
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )


async def cmd_downloadsheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return

    await update.message.reply_text("⏳ Generating sheet, please wait...")

    subs = db.get_approved_submissions()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Submission ID", "User ID", "Username", "Task Name", "Reward ($)", "Proof / ID", "Date"])

    for s in subs:
        writer.writerow([
            s.get("submission_id", ""),
            s.get("user_id", ""),
            s.get("username", ""),
            s.get("title", ""),
            f"{s.get('reward', 0):.4f}",
            s.get("proof", ""),
            s.get("approved_at", ""),
        ])

    output.seek(0)
    csv_bytes = output.getvalue().encode("utf-8")

    filename = f"instant_money_bux_tasks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    await update.message.reply_document(
        document=InputFile(io.BytesIO(csv_bytes), filename=filename),
        caption=(
            f"📥 *Task Submissions Sheet*\n\n"
            f"Total records: `{len(subs)}`\n"
            f"Generated: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            f"Use this CSV to check Live IDs against the Proof/ID column."
        ),
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )


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


async def cmd_toggle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only the owner can toggle the task system.")
        return

    config.TASK_SYSTEM_ENABLED = not config.TASK_SYSTEM_ENABLED
    state = "ENABLED ✅" if config.TASK_SYSTEM_ENABLED else "DISABLED ❌"
    await update.message.reply_text(f"Task system is now *{state}*.", parse_mode="Markdown")


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
        lines.append(
            f"{name}: bal=`${total_bal:.4f}` refs=`{len(refs)}` tasks=`{tasks}` wds=`{len(wds)}`"
        )

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
        f"Pending withdrawal requests: `${pending_total:.4f}`\n"
        f"Total paid out (approved): `${approved_total:.4f}`\n\n"
        f"{'✅ Sufficient funds for pending.' if total_balances >= pending_total else '⚠️ Insufficient funds for pending withdrawals!'}",
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
            lines.append(
                f"⚠️ {name} (`{u['user_id']}`): {len(referrals)} refs, {completed} completed — SUSPICIOUS"
            )

    if len(lines) == 1:
        await update.message.reply_text("✅ No suspicious fake referral activity detected.")
    else:
        await update.message.reply_text("\n".join(lines[:30]), parse_mode="Markdown")


async def start_create_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END

    await update.message.reply_text(
        "➕ *Create New Task*\n\nStep 1: Enter the task title:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return CREATE_TITLE


async def receive_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    context.user_data["new_task_title"] = update.message.text.strip()
    await update.message.reply_text("Step 2: Enter the task description:")
    return CREATE_DESC


async def receive_task_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ConversationHandler.END

    context.user_data["new_task_desc"] = update.message.text.strip()
    await update.message.reply_text("Step 3: Enter the reward amount (e.g. 0.05):")
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

    title = context.user_data.get("new_task_title")
    desc = context.user_data.get("new_task_desc")
    task_id = db.create_task(title, desc, reward, update.effective_user.id)

    await update.message.reply_text(
        f"✅ Task created!\n\nID: `{task_id}`\nTitle: *{title}*\nReward: `${reward:.4f}`",
        parse_mode="Markdown",
        reply_markup=ADMIN_MENU,
    )
    return ConversationHandler.END


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
        lines.append(f"ID `{t['task_id']}`: *{t['title']}* — `${t['reward']:.4f}`")
    lines.append("\nUse /deltask <task_id> to remove a task.")
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
    await update.message.reply_text(f"✅ Task `{task_id}` has been deactivated.", parse_mode="Markdown")


async def start_livereport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📡 *Live ID Report*\n\n"
        "Upload a file with Live IDs (CSV, XLSX, or TXT).\n"
        "The bot will compare them against submitted proofs and auto-add bonuses to matched users.\n\n"
        "💡 *Tip:* Download the task sheet first (`📥 Download Sheet`) to see all submitted IDs.",
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
            import csv as _csv
            reader = _csv.reader(io.StringIO(content))
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

    approved_proof_ids = db.get_approved_proof_ids()

    matched_users = {}
    for live_id in live_ids:
        if live_id in approved_proof_ids:
            users = db.get_live_id_matches_by_live_id(live_id)
            for u in users:
                if u["user_id"] not in matched_users:
                    matched_users[u["user_id"]] = {"username": u["username"], "ids": []}
                matched_users[u["user_id"]]["ids"].append(live_id)

    bonus_per_id = config.LIVE_ID_BONUS_PER_ID
    total_bonus_given = 0

    for user_id, info in matched_users.items():
        bonus = bonus_per_id * len(info["ids"])
        db.update_user_balance(user_id, bonus, "balance")
        db.add_transaction(user_id, "live_id_bonus", bonus, "Live ID match bonus")
        total_bonus_given += bonus
        for lid in info["ids"]:
            db.add_live_id_match(user_id, lid, bonus_per_id)
        try:
            await context.bot.send_message(
                user_id,
                f"🎉 Your Live ID was matched!\nBonus added: `${bonus:.4f}`",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    total_matched = sum(len(info["ids"]) for info in matched_users.values())
    summary_lines = [
        "📡 *Live ID Report Summary*\n",
        f"Live IDs uploaded: `{len(live_ids)}`",
        f"Matched IDs: `{total_matched}`",
        f"Matched users: `{len(matched_users)}`",
        f"Bonus per ID: `${bonus_per_id:.4f}`",
        f"Total bonus distributed: `${total_bonus_given:.4f}`",
        f"Unmatched IDs: `{len(live_ids) - total_matched}`",
    ]

    if matched_users:
        summary_lines.append("\n*Matched Users:*")
        for uid, info in list(matched_users.items())[:20]:
            name = f"@{info['username']}" if info.get("username") else str(uid)
            summary_lines.append(f"{name}: {len(info['ids'])} ID(s) → `${bonus_per_id * len(info['ids']):.4f}`")

    await update.message.reply_text(
        "\n".join(summary_lines), parse_mode="Markdown", reply_markup=ADMIN_MENU
    )
    return ConversationHandler.END


async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
    return ConversationHandler.END


create_task_conv = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^➕ Create Task$"), start_create_task),
        CommandHandler("createtask", start_create_task),
    ],
    states={
        CREATE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_title)],
        CREATE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_desc)],
        CREATE_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_reward)],
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
