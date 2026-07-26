import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import yt_dlp
import asyncio

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
AUTHORIZED_USER = os.environ.get("AUTHORIZED_USER")  # optional

def is_authorized(user_id: int) -> bool:
    if not AUTHORIZED_USER:
        return True
    try:
        return str(user_id) == str(AUTHORIZED_USER)
    except Exception:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! ربات آماده است.")

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        if not is_authorized(user.id):
            await update.message.reply_text("شما مجاز نیستید.")
            return

        text = update.message.text.strip()
        url = text.split()[0]  # ساده‌سازی: اولین کلمه را URL فرض می‌کنیم
        await update.message.reply_text("در حال دانلود...")

        ydl_opts = {
            "format": "mp4",
            "outtmpl": "video.mp4",
            "quiet": True,
            "no_warnings": True,
        }

        # اجرای yt-dlp در thread جدا تا حلقهٔ async مسدود نشود
        loop = asyncio.get_running_loop()
        def run_ydl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await loop.run_in_executor(None, run_ydl)

        # ارسال ویدیو
        with open("video.mp4", "rb") as f:
            await update.message.reply_video(video=f)
    except Exception as e:
        logger.exception("Download error")
        await update.message.reply_text(f"❌ خطا: {e}")

def build_app():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download))
    return app

def main():
    app = build_app()
    logger.info("Bot started...")
    # run_polling مدیریت حلقهٔ asyncio را خودش انجام می‌دهد؛
    # **هیچ** asyncio.run یا loop.run_until_complete در سطح ماژول نباید باشد.
    app.run_polling()

if __name__ == "__main__":
    main()
