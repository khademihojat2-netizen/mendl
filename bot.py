# bot.py (اصلاح‌شده)

import asyncio
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "..."  # از متغیر محیطی استفاده کنید
AUTHORIZED_USER = 123456789

def is_authorized(user_id: int) -> bool:
    return user_id == AUTHORIZED_USER

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! آماده‌ام.")

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("دسترسی ندارید.")
        return

    url = update.message.text.strip()
    if not url:
        await update.message.reply_text("لینک را ارسال کنید.")
        return

    await update.message.reply_text("در حال دانلود... لطفاً صبر کنید.")

    ydl_opts = {
        "format": "mp4",
        "outtmpl": "video.mp4",
    }

    try:
        # اجرای دانلود در ترد جدا تا حلقهٔ async مسدود نشود
        await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))

        # ارسال و بستن فایل به‌صورت امن
        with open("video.mp4", "rb") as f:
            await update.message.reply_video(video=f)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(...)
    await app.initialize()
    await app.start()
    try:
        await app.updater.start_polling()
        await asyncio.Event().wait()  # نگه داشتن برنامه
    finally:
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())

