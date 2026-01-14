import os
import sqlite3
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TZ = ZoneInfo("Europe/Berlin")  # MEZ/MESZ automatisch
DB_PATH = os.getenv("DB_PATH", "bot.db")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TASK1_URL = os.getenv("TASK1_URL")
TASK2_URL = os.getenv("TASK2_URL")
TASK3_URL = os.getenv("TASK3_URL")


WELCOME_TEXT = "Hello,\nClick and solve all of them to get the code."

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL;")
    return con

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_code (
            day TEXT PRIMARY KEY,
            code TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_progress (
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            task1 INTEGER NOT NULL DEFAULT 0,
            task2 INTEGER NOT NULL DEFAULT 0,
            task3 INTEGER NOT NULL DEFAULT 0,
            sent  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day)
        )
    """)
    con.commit()
    con.close()

def today_str() -> str:
    return datetime.now(TZ).date().isoformat()

def generate_code() -> str:
    return f"{secrets.randbelow(10**8):08d}"  # 8-stellig

def get_or_create_daily_code(day: str) -> str:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT code FROM daily_code WHERE day=?", (day,))
    row = cur.fetchone()
    if row:
        con.close()
        return row[0]

    code = generate_code()
    cur.execute("INSERT INTO daily_code(day, code) VALUES(?, ?)", (day, code))
    con.commit()
    con.close()
    return code

def get_progress(user_id: int, day: str):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT task1, task2, task3, sent
        FROM user_progress
        WHERE user_id=? AND day=?
    """, (user_id, day))
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO user_progress(user_id, day, task1, task2, task3, sent)
            VALUES(?, ?, 0, 0, 0, 0)
        """, (user_id, day))
        con.commit()
        row = (0, 0, 0, 0)
    con.close()
    return row

def set_task_done(user_id: int, day: str, task_num: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO user_progress(user_id, day, task1, task2, task3, sent)
        VALUES(?, ?, 0, 0, 0, 0)
        ON CONFLICT(user_id, day) DO NOTHING
    """, (user_id, day))
    cur.execute(f"UPDATE user_progress SET task{task_num}=1 WHERE user_id=? AND day=?", (user_id, day))
    con.commit()
    con.close()

def mark_sent(user_id: int, day: str):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE user_progress SET sent=1 WHERE user_id=? AND day=?", (user_id, day))
    con.commit()
    con.close()

def all_done(t1, t2, t3) -> bool:
    return t1 == 1 and t2 == 1 and t3 == 1

def task_keyboard(t1: int, t2: int, t3: int) -> InlineKeyboardMarkup:
    def label(n, done):
        return f"Task {n} ✅" if done else f"Task {n}"

    kb = [
        [InlineKeyboardButton(label(1, t1), url=TASK1_URL)],
        [InlineKeyboardButton(label(2, t2), url=TASK2_URL)],
        [InlineKeyboardButton(label(3, t3), url=TASK3_URL)],
    ]
    return InlineKeyboardMarkup(kb)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    day = today_str()
    get_or_create_daily_code(day)
    t1, t2, t3, _sent = get_progress(user_id, day)

    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=task_keyboard(t1, t2, t3)
    )

async def on_task_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    day = today_str()
    code = get_or_create_daily_code(day)

    task_num = int(query.data.split(":")[1])
    set_task_done(user_id, day, task_num)

    t1, t2, t3, sent = get_progress(user_id, day)

    # Buttons aktualisieren (✅)
    await query.edit_message_reply_markup(reply_markup=task_keyboard(t1, t2, t3))

    # Wenn alle 3 erledigt und Code noch nicht gesendet → senden
    if all_done(t1, t2, t3) and sent == 0:
        mark_sent(user_id, day)
        await query.message.reply_text(f"✅ Your code for today: `{code}`", parse_mode="Markdown")

async def daily_midnight_job(context: ContextTypes.DEFAULT_TYPE):
    # erzeugt den neuen Code für den neuen Tag
    get_or_create_daily_code(today_str())

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN fehlt. Setze ihn in Railway -> Variables.")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_task_click, pattern=r"^task:\d$"))

    # täglich 00:00 (Europe/Berlin)
    app.job_queue.run_daily(
        daily_midnight_job,
        time=datetime.strptime("00:00", "%H:%M").time(),
        days=(0, 1, 2, 3, 4, 5, 6),
        name="daily_code_job",
    )

    # beim Start sicherstellen: Code existiert
    get_or_create_daily_code(today_str())

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
44
