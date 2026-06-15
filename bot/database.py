import sqlite3
import os
from datetime import datetime
from config import DB_PATH


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            referral_bonus REAL DEFAULT 0.0,
            referred_by INTEGER,
            is_banned INTEGER DEFAULT 0,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            reward REAL NOT NULL,
            created_by INTEGER,
            is_active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id INTEGER,
            proof TEXT,
            status TEXT DEFAULT 'pending',
            approved_by INTEGER,
            approved_at TEXT,
            sheet_logged INTEGER DEFAULT 0,
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            withdrawal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            payment_method TEXT,
            account_details TEXT,
            status TEXT DEFAULT 'pending',
            approved_by INTEGER,
            processed_at TEXT,
            requested_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            referral_id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus_earned REAL DEFAULT 0.0,
            task_completed INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            description TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS live_id_matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            live_id TEXT,
            bonus_added REAL,
            report_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(user_id: int, username: str, referred_by: int = None):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, referred_by) VALUES (?,?,?)",
        (user_id, username, referred_by),
    )
    conn.commit()
    conn.close()


def update_user_balance(user_id: int, amount: float, field: str = "balance"):
    conn = get_conn()
    conn.execute(f"UPDATE users SET {field}={field}+? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()


def set_user_banned(user_id: int, banned: bool):
    conn = get_conn()
    conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (1 if banned else 0, user_id))
    conn.commit()
    conn.close()


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_tasks():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tasks WHERE is_active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task(task_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_task(title: str, description: str, reward: float, created_by: int):
    conn = get_conn()
    c = conn.execute(
        "INSERT INTO tasks (title, description, reward, created_by) VALUES (?,?,?,?)",
        (title, description, reward, created_by),
    )
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    return task_id


def delete_task(task_id: int):
    conn = get_conn()
    conn.execute("UPDATE tasks SET is_active=0 WHERE task_id=?", (task_id,))
    conn.commit()
    conn.close()


def create_submission(user_id: int, task_id: int, proof: str):
    conn = get_conn()
    c = conn.execute(
        "INSERT INTO submissions (user_id, task_id, proof) VALUES (?,?,?)",
        (user_id, task_id, proof),
    )
    sub_id = c.lastrowid
    conn.commit()
    conn.close()
    return sub_id


def get_submission(submission_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM submissions WHERE submission_id=?", (submission_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_submissions():
    conn = get_conn()
    rows = conn.execute(
        "SELECT s.*, u.username, t.title, t.reward FROM submissions s "
        "JOIN users u ON s.user_id=u.user_id "
        "JOIN tasks t ON s.task_id=t.task_id "
        "WHERE s.status='pending'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_submission_status(submission_id: int, status: str, approved_by: int):
    conn = get_conn()
    conn.execute(
        "UPDATE submissions SET status=?, approved_by=?, approved_at=? WHERE submission_id=?",
        (status, approved_by, datetime.now().isoformat(), submission_id),
    )
    conn.commit()
    conn.close()


def mark_submission_logged(submission_id: int):
    conn = get_conn()
    conn.execute("UPDATE submissions SET sheet_logged=1 WHERE submission_id=?", (submission_id,))
    conn.commit()
    conn.close()


def get_approved_submissions():
    conn = get_conn()
    rows = conn.execute(
        "SELECT s.*, u.username, t.title FROM submissions s "
        "JOIN users u ON s.user_id=u.user_id "
        "JOIN tasks t ON s.task_id=t.task_id "
        "WHERE s.status='approved'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_withdrawal(user_id: int, amount: float, method: str, details: str):
    conn = get_conn()
    c = conn.execute(
        "INSERT INTO withdrawals (user_id, amount, payment_method, account_details) VALUES (?,?,?,?)",
        (user_id, amount, method, details),
    )
    wid = c.lastrowid
    conn.commit()
    conn.close()
    return wid


def get_withdrawal(withdrawal_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM withdrawals WHERE withdrawal_id=?", (withdrawal_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_withdrawals():
    conn = get_conn()
    rows = conn.execute(
        "SELECT w.*, u.username FROM withdrawals w JOIN users u ON w.user_id=u.user_id WHERE w.status='pending'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_withdrawal_status(withdrawal_id: int, status: str, approved_by: int):
    conn = get_conn()
    conn.execute(
        "UPDATE withdrawals SET status=?, approved_by=?, processed_at=? WHERE withdrawal_id=?",
        (status, approved_by, datetime.now().isoformat(), withdrawal_id),
    )
    conn.commit()
    conn.close()


def get_user_withdrawals(user_id: int):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM withdrawals WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_transaction(user_id: int, type_: str, amount: float, description: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO transactions (user_id, type, amount, description) VALUES (?,?,?,?)",
        (user_id, type_, amount, description),
    )
    conn.commit()
    conn.close()


def create_referral(referrer_id: int, referred_id: int):
    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM referrals WHERE referred_id=?", (referred_id,)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO referrals (referrer_id, referred_id) VALUES (?,?)",
            (referrer_id, referred_id),
        )
        conn.commit()
    conn.close()


def get_referral_by_referred(referred_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM referrals WHERE referred_id=?", (referred_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_referral_completed(referred_id: int, bonus: float):
    conn = get_conn()
    conn.execute(
        "UPDATE referrals SET task_completed=1, bonus_earned=? WHERE referred_id=?",
        (bonus, referred_id),
    )
    conn.commit()
    conn.close()


def get_referrals_by_referrer(referrer_id: int):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM referrals WHERE referrer_id=?", (referrer_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_task_count(user_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM submissions WHERE user_id=? AND status='approved'",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_all_task_stats():
    conn = get_conn()
    rows = conn.execute(
        "SELECT u.user_id, u.username, COUNT(s.submission_id) as completed "
        "FROM users u LEFT JOIN submissions s ON u.user_id=s.user_id AND s.status='approved' "
        "GROUP BY u.user_id ORDER BY completed DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_withdraw_stats():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM withdrawals ORDER BY requested_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_live_id_matches_by_live_id(live_id: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT s.user_id, u.username FROM submissions s "
        "JOIN users u ON s.user_id=u.user_id "
        "WHERE s.proof=? AND s.status='approved'",
        (live_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_live_id_match(user_id: int, live_id: str, bonus: float):
    conn = get_conn()
    conn.execute(
        "INSERT INTO live_id_matches (user_id, live_id, bonus_added) VALUES (?,?,?)",
        (user_id, live_id, bonus),
    )
    conn.commit()
    conn.close()


def get_approved_proof_ids():
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT proof FROM submissions WHERE status='approved'"
    ).fetchall()
    conn.close()
    return {r["proof"] for r in rows}
