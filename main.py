from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import logging
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")

# fires for any non-command text
async def onUpdateReceived(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # dice (includes 🎰 slot machine)
    if msg.dice:
        user = msg.from_user
        d = msg.dice
        await asyncio.sleep(1.5)
        if d.value == 64:
            print(f"User: {user.username} Just Hit the JACKPOT! CONGRATS!")
            await msg.reply_text(f"User: {user.username} Just Hit the JACKPOT!")

        elif d.value == 22 or d.value == 43 or d.value == 1:
            print(f"User: {user.username} Got 3 in a ROW!")
            await msg.reply_text(f"User: {user.username} Got 3 in a ROW!")

        print(f"Dice {d.emoji} = {d.value}")
        #await msg.reply_text(f"{d.emoji} rolled {d.value}")
        return

    # regular text
    if msg.text:
        user = msg.from_user
        print(f"User {user.username} ({user.id}) said: {msg.text}")
        # your text handling here...


def main():
    #Declaring all the ENVs
    botToken = os.getenv("ENV_BOTTOKEN")
    webhook_url = os.getenv("WEBHOOK_URL")
    secret = os.getenv("WEBHOOK_SECRET")  # optional
    port = int(os.getenv("PORT", "8080"))

    if not botToken:
        raise RuntimeError("Missing BOT_TOKEN")
    if not webhook_url:
        raise RuntimeError("Missing WEBHOOK_URL")

    app = Application.builder().token(botToken).build()
    app.add_handler(CommandHandler("start", start))

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="",
        webhook_url=webhook_url
    )

    # Combine filters: text (non-command) OR any dice OR any sticker
    # PTB v21+: use filters.Dice.ALL; older PTB: use filters.DICE
    dice_filter = getattr(filters.Dice, "ALL", getattr(filters, "Dice"))

    # receive text & dice in groups and supergroups
    group_filter = filters.ChatType.GROUPS & ((filters.TEXT & ~filters.COMMAND) | getattr(filters.Dice, "ALL", getattr(filters, "Dice")))
    combo = (filters.TEXT & ~filters.COMMAND) | dice_filter | filters.Sticker.ALL

    app.add_handler(MessageHandler(combo, onUpdateReceived))
    app.add_handler(MessageHandler(group_filter, onUpdateReceived))

    app.run_polling()

if __name__ == "__main__":
    main()