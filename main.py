# main.py
import os
import asyncio
from urllib.parse import urlparse
import asyncpg
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
load_dotenv()

# =========================
# Config / DB helpers
# =========================
DB_URL = os.getenv("DATABASE_URL")
_pool: asyncpg.Pool | None = None

async def init_db():
    """Called once on startup (you already do asyncio.run(init_db()))."""
    global _pool
    if not DB_URL:
        raise RuntimeError("Missing DATABASE_URL")
    _pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
              chat_id  BIGINT PRIMARY KEY,
              username TEXT,
              user_id  BIGINT,
              name     TEXT
            )
        """)

async def set_contact_db(chat_id: int, username: str | None, user_id: int | None, name: str | None):
    async with _pool.acquire() as conn:
        await conn.execute("""
          INSERT INTO contacts (chat_id, username, user_id, name)
          VALUES ($1, $2, $3, $4)
          ON CONFLICT (chat_id) DO UPDATE SET
            username = EXCLUDED.username,
            user_id  = EXCLUDED.user_id,
            name     = EXCLUDED.name
        """, chat_id, username, user_id, name)

async def get_contact_db(chat_id: int):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username, user_id, name FROM contacts WHERE chat_id=$1", chat_id
        )
        return (row["username"], row["user_id"], row["name"]) if row else None

async def unset_contact_db(chat_id: int):
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM contacts WHERE chat_id=$1", chat_id)

# =========================
# Admin check
# =========================
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False
    m = await context.bot.get_chat_member(chat.id, user.id)
    return m.status in ("creator", "administrator")

# =========================
# Commands
# =========================
async def set_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Only group admins can set the contact.")

    chat_id = update.effective_chat.id
    username = None
    user_id = None
    name = None

    # /setcontact @Username
    if context.args and context.args[0].startswith("@") and len(context.args[0]) > 1:
        username = context.args[0][1:]
    # Or: reply to a user with /setcontact
    elif update.message.reply_to_message:
        u = update.message.reply_to_message.from_user
        user_id = u.id
        name = u.full_name

    if not username and not user_id:
        return await update.message.reply_text("Usage: /setcontact @username  (or reply to a user with /setcontact)")

    await set_contact_db(chat_id, username, user_id, name)
    who = f"@{username}" if username else (name or "this user")
    await update.message.reply_text(f"Contact set to {who} for this group ✅")

async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    row = await get_contact_db(chat_id)
    if not row:
        return await update.message.reply_text("No contact set for this group.")
    username, uid, name = row
    if username:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Message @{username}", url=f"https://t.me/{username}")]])
        return await update.message.reply_text(f"Current contact: @{username}", reply_markup=kb)
    link = f'<a href="tg://user?id={uid}">{name or "this user"}</a>'
    return await update.message.reply_text(f"Current contact: {link}", parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def unset_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Only group admins can unset the contact.")
    await unset_contact_db(update.effective_chat.id)
    await update.message.reply_text("Contact cleared for this group.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")

# =========================
# Message handler
# =========================
async def onUpdateReceived(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # Dice (includes 🎰 slot machine)
    if msg.dice:
        user = msg.from_user
        d = msg.dice
        await asyncio.sleep(1.5)

        if d.value == 64:
            # Jackpot text + contact for this chat if set
            row = await get_contact_db(update.effective_chat.id)
            contact_line = ""
            reply_markup = None
            parse_mode = None
            if row:
                username, uid, name = row
                if username:
                    contact_line = f"\n\nPlease contact @{username} to claim your prize!"
                    reply_markup = InlineKeyboardMarkup(
                        [[InlineKeyboardButton(f"Message @{username}", url=f"https://t.me/{username}")]]
                    )
                elif uid:
                    contact_line = f'\nPlease contact <a href="tg://user?id={uid}">{name or "this user"}</a>'
                    parse_mode = ParseMode.HTML

            text = f"User: {user.username} Just Hit the JACKPOT!{contact_line}"
            await msg.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)

        elif d.value in {1, 22, 43}:
            await msg.reply_text(f"User: {user.username} Got 3 in a ROW!")

        # simple log
        print(f"Dice {d.emoji} = {d.value}")
        return

    # Regular text
    if msg.text:
        user = msg.from_user
        print(f"User {user.username} ({user.id}) said: {msg.text}")

# =========================
# App bootstrap
# =========================
def main():
    # Env
    bot_token  = os.getenv("ENV_BOTTOKEN")          # you chose this name; keeping it
    webhook_url = os.getenv("WEBHOOK_URL")
    secret      = os.getenv("WEBHOOK_SECRET")       # optional
    port        = int(os.getenv("PORT", "8080"))

    if not bot_token:
        raise RuntimeError("Missing ENV_BOTTOKEN")
    if not webhook_url:
        raise RuntimeError("Missing WEBHOOK_URL")

    # Ensure DB exists before starting bot loop
    asyncio.run(init_db())

    # Build app & handlers
    app = Application.builder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setcontact", set_contact))
    app.add_handler(CommandHandler("getcontact", get_contact))
    app.add_handler(CommandHandler("unsetcontact", unset_contact))

    # Filters (separate for groups vs private, as you wanted)
    dice_filter    = filters.Dice.ALL
    text_filter    = filters.TEXT & ~filters.COMMAND
    group_filter   = filters.ChatType.GROUPS  & (text_filter | dice_filter)
    private_filter = filters.ChatType.PRIVATE & (text_filter | dice_filter | filters.Sticker.ALL)

    app.add_handler(MessageHandler(group_filter, onUpdateReceived))
    app.add_handler(MessageHandler(private_filter, onUpdateReceived))

    # Webhook path must match WEBHOOK_URL path
    path = urlparse(webhook_url).path.lstrip("/")

    async def _post_init(app):
        await init_db()

    app.post_init = _post_init

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=path,               # must match the path in WEBHOOK_URL
        webhook_url=webhook_url,
        secret_token=secret,         # optional
    )

if __name__ == "__main__":
    main()