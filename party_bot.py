"""
Party Bot - وقتی کسی وارد گروه تلگرام میشه (یا با دستور /party)، دکمه Mini App
پارتی رو میفرسته. با باز شدن Mini App، صفحه خودش یه آهنگ رندوم از Jamendo
(قانونی/Royalty-free) میگیره و بلافاصله پخش میکنه + نورهای پارتی روشن میشه.

قابلیت‌ها:
- خوش‌آمد خودکار به اعضای جدید با دکمه ورود به مهمونی
- دستور دستی /party برای شروع مهمونی هر موقع که بخوای
- پیام خداحافظی وقتی کسی گروه رو ترک می‌کنه
- شمارنده‌ی تعداد دفعاتی که مهمونی شروع شده (در حافظه)
- هندلر خطا تا کرش نکنه اگه یه درخواست به تلگرام fail بشه

نصب:
    pip install python-telegram-bot==21.4 requests

اجرا:
    python party_bot.py
"""

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# ---------------- تنظیمات ----------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
# لینک مستقیم Mini App که از BotFather (/newapp) گرفتی، شبیه:
# https://t.me/USERNAME_BOT/party
MINI_APP_DEEPLINK = os.environ["MINI_APP_DEEPLINK"]

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("party_bot")

# شمارنده‌ی ساده در حافظه (با ری‌استارت بات صفر میشه؛ برای شمارش دائمی
# بعداً میشه یه دیتابیس سبک مثل SQLite اضافه کرد)
party_count = {}  # chat_id -> تعداد دفعات شروع مهمونی


def party_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ورود به مهمونی 🎉", url=MINI_APP_DEEPLINK)]
    ])


async def welcome_with_party_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    chat_id = update.effective_chat.id
    names = ", ".join(m.first_name for m in update.message.new_chat_members)
    party_count[chat_id] = party_count.get(chat_id, 0) + 1

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"خوش اومدی {names}! برای شروع موزیک و نورهای پارتی دکمه زیر رو بزن 👇",
        reply_markup=party_button(),
    )


async def goodbye_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    left = update.message.left_chat_member
    if not left:
        return
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{left.first_name} از مهمونی رفت 👋 امیدواریم خوش گذشته باشه!",
    )


async def party_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور دستی /party - هرکسی توی گروه میتونه مهمونی رو دستی شروع کنه."""
    chat_id = update.effective_chat.id
    party_count[chat_id] = party_count.get(chat_id, 0) + 1

    await update.message.reply_text(
        "مهمونی شروع شد! 🎊 دکمه زیرو بزن:",
        reply_markup=party_button(),
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /partystats - تعداد دفعاتی که مهمونی توی این گروه شروع شده."""
    chat_id = update.effective_chat.id
    count = party_count.get(chat_id, 0)
    await update.message.reply_text(f"🎉 تا الان {count} بار مهمونی توی این گروه شروع شده!")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! برای ورود به مهمونی دکمه زیر رو بزن 👇",
        reply_markup=party_button(),
    )


async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر مرکزی خطا - جای کرش کردن، فقط لاگ میکنه."""
    log.error("خطا هنگام پردازش یه آپدیت: %s", context.error, exc_info=context.error)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("party", party_command))
    app.add_handler(CommandHandler("partystats", stats_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_with_party_button))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye_message))
    app.add_error_handler(error_handler)

    log.info("Party bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
