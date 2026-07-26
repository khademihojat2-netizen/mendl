# bot.py
import os
import logging
import tempfile
from pathlib import Path

import yt_dlp
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Configuration from environment ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
AUTHORIZED_USER = os.environ.get("AUTHORIZED_USER")  # optional: Telegram user id as string

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Helpers ---
def is_authorized(user_id: int) -> bool:
    if AUTHORIZED_USER is None:
        return True
    try:
        return str(user_id) == str(AUTHORIZED_USER)
    except Exception:
        return False

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name}!\nلطفا لینک ویدیو را ارسال کنید تا دانلود و ارسال شود."
    )

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    if not is_authorized(user.id):
        await msg.reply_text("شما مجاز نیستید.")
        return

    text = msg.text.strip()
    url = text.split()[0] if text else None
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        await msg.reply_text("لطفا یک لینک معتبر ارسال کنید.")
        return

    await msg.reply_text("در حال دانلود... لطفا صبر کنید.")
    try:
        # use a temporary file to avoid collisions
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "video.%(ext)s"
            ydl_opts = {
                "format": "mp4/best",
                "outtmpl": str(out_path),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "retries": 3,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # find downloaded filename
                filename = ydl.prepare_filename(info)
                # ensure mp4 extension if possible
                if not Path(filename).exists():
                    # try to find any file in tmpdir
                    files = list(Path(tmpdir).glob("*"))
                    if files:
                        filename = str(files[0])
                # send video (use reply_video for Telegram)
                with open(filename, "rb") as f:
                    await msg.reply_video(video=f)
    except Exception as e:
        logger.exception("Download failed")
        await msg.reply_text(f"❌ خطا در دانلود یا ارسال ویدیو:\n{e}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ارسال لینک ویدیو برای دانلود. فقط mp4 یا فرمت‌های پشتیبانی‌شده.")

# --- Main (synchronous) ---
def main():
    # Build application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler))

    logger.info("Bot started...")
    # run_polling is blocking and manages its own event loop internally
    app.run_polling()

if __name__ == "__main__":
    main()
