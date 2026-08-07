"""
Party Bot - وقتی کسی وارد گروه تلگرام میشه، دکمه Mini App پارتی رو میفرسته.
با باز شدن Mini App (یه تاچ)، صفحه خودش یه آهنگ رندوم از Jamendo
(قانونی/Royalty-free) میگیره و بلافاصله پخش میکنه + نورهای پارتی روشن میشه.

نصب:
    pip install python-telegram-bot==21.4 requests

اجرا:
    python party_bot.py
"""

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------- تنظیمات ----------------
# از Environment Variables توی Railway خونده میشه.
BOT_TOKEN = os.environ["BOT_TOKEN"]
MINI_APP_URL = os.environ["MINI_APP_URL"]  # لینک https صفحه party-entrance.html که هاست کردی

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("party_bot")


async def welcome_with_party_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    chat_id = update.effective_chat.id
    names = ", ".join(m.first_name for m in update.message.new_chat_members)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ورود به مهمونی 🎉", web_app=WebAppInfo(url=MINI_APP_URL))]
    ])

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"خوش اومدی {names}! برای شروع موزیک و نورهای پارتی دکمه زیر رو بزن 👇",
        reply_markup=keyboard,
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_with_party_button))
    log.info("Party bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
