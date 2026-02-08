import os
import logging
import time
import random
import string
import aiohttp

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# ================= CONFIG =================
BOT_TOKEN = os.getenv("8331667464:AAH2hkwR18D-yHNE1OCMNm12MdzUbm7OUpo")
ADMIN_ID = int(os.getenv("6582969543", "0"))

API_BASE = "https://api.cavira.vip"

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("Missing BOT_TOKEN or ADMIN_ID")

ALLOWED_USERS = {ADMIN_ID}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("railway-bot")

# ================= STATE =================
accounts_queue = []
active_sessions = {}
monitored_numbers = {}

# ================= HELPERS =================
def uuid17():
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(17))

def headers(token=""):
    return {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://cavira.vip",
        "Referer": "https://cavira.vip/",
        "x-token": token,
    }

def is_admin(uid):
    return uid in ALLOWED_USERS

def dur(sec):
    m, _ = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m"

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Access denied")

    kb = [[KeyboardButton("📂 Upload"), KeyboardButton("📊 Status")]]
    await update.message.reply_text(
        "🤖 Bot Online (Railway Stable)",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

# ================= STATUS =================
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not monitored_numbers:
        return await update.message.reply_text("📭 No data")

    now = time.time()
    text = "📊 Status\n\n"
    for i, (p, d) in enumerate(monitored_numbers.items(), 1):
        text += f"{i}. {p} | {d['email']} | {dur(now-d['t'])}\n"

    await update.message.reply_text(text)

# ================= FILE =================
async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    f = await update.message.document.get_file()
    data = (await f.download_as_bytearray()).decode().splitlines()

    accounts_queue.clear()
    buf = None
    for l in data:
        l = l.strip()
        if not l:
            continue
        if not buf:
            buf = l
        else:
            accounts_queue.append({"email": buf, "password": l})
            buf = None

    await update.message.reply_text(f"✅ Loaded {len(accounts_queue)} accounts")
    await next_account(update, context)

# ================= PROCESS =================
async def next_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not accounts_queue:
        return await update.message.reply_text("🏁 Done")

    acc = accounts_queue.pop(0)

    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{API_BASE}/h5/taskBase/login",
            json=acc, headers=headers()
        ) as r:
            data = await r.json()

    if data.get("code") != 0:
        return await next_account(update, context)

    token = data["data"]["token"]
    active_sessions[acc["email"]] = token
    context.user_data["email"] = acc["email"]

    await update.message.reply_text("📱 Send phone number")

# ================= PHONE =================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    txt = update.message.text

    if txt == "📊 Status":
        return await status(update, context)

    if not txt.isdigit():
        return

    email = context.user_data.get("email")
    if not email:
        return

    uid = uuid17()
    token = active_sessions[email]

    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{API_BASE}/h5/taskUser/phoneCode",
            json={"uuid": uid, "phone": txt, "type": 2},
            headers=headers(token)
        ) as r:
            data = await r.json()

    if data.get("code") != 0:
        return await update.message.reply_text("❌ Failed")

    await update.message.reply_text(
        f"📟 Code: {data['data']['phone_code']}"
    )

    monitored_numbers[txt] = {
        "email": email,
        "t": time.time()
    }

    await next_account(update, context)

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Bot started successfully (Polling Mode)")
    app.run_polling()

if __name__ == "__main__":
    main()