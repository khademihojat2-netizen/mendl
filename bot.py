import os
import logging
import yt_dlp
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# لاگ برای دیباگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUTHORIZED_USER = os.getenv("AUTHORIZED_USER")

def is_authorized(update: Update) -> bool:
    if not AUTHORIZED_USER:
        return True
    return str(update.effective_user.id) == str(AUTHORIZED_USER)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ شما مجاز به استفاده از این بات نیستید.")
        return
    await update.message.reply_text("سلام 👋 لینک یوتیوب بفرست تا دانلود کنم.")

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ شما مجاز به استفاده از این بات نیستید.")
        return

    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("❌ لطفاً لینک معتبر بفرست.")
        return

    await update.message.reply_text("⏳ در حال دانلود...")

    try:
        ydl_opts = {"format": "mp4", "outtmpl": "video.mp4"}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        with open("video.mp4", "rb") as f:
            await update.message.reply_video(video=f)

    except Exception as e:
        logger.exception("خطا در دانلود")
        await update.message.reply_text(f"❌ خطا:\n{e}")

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download))
    print("Bot started...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except RuntimeError as e:
        # اگر Railway گفت loop در حال اجراست، از loop موجود استفاده کن
        loop = asyncio.get_event_loop()
        loop.create_task(main())
        loop.run_forever()
