"""
Party Bot - وقتی کسی وارد گروه تلگرام میشه، خودکار یه آهنگ پارتی رندوم
از Jamendo (Royalty-free / قانونی) پخش میکنه.

نصب:
    pip install python-telegram-bot==21.4 requests

اجرا:
    python party_bot.py
"""

import os
import random
import logging
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    ChatMemberHandler,
    MessageHandler,
    filters,
)

# ---------------- تنظیمات ----------------
# این دوتا رو دیگه توی کد نمی‌نویسیم؛ از Environment Variables توی Railway می‌خونیم.
BOT_TOKEN = os.environ["BOT_TOKEN"]
JAMENDO_CLIENT_ID = os.environ["JAMENDO_CLIENT_ID"]

MAX_DURATION_SECONDS = 240          # کمتر از ۴ دقیقه
TAGS = "party+dance+electronic"     # ژانرهای پارتی
RESULTS_PER_FETCH = 30              # هر بار چندتا کاندید بگیره تا رندوم انتخاب کنه

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("party_bot")

# جلوگیری از تکرار آهنگ اخیر، به ازای هر گروه
recent_tracks = {}  # chat_id -> set of track ids


def fetch_random_track(chat_id: int):
    """یه آهنگ رندوم پارتی زیر ۴ دقیقه از Jamendo میگیره."""
    params = {
        "client_id": JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": RESULTS_PER_FETCH,
        "tags": TAGS,
        "durationbetween": f"30_{MAX_DURATION_SECONDS}",
        "order": "popularity_total",
        "audioformat": "mp32",
    }
    resp = requests.get("https://api.jamendo.com/v3.0/tracks/", params=params, timeout=10)
    resp.raise_for_status()
    tracks = resp.json().get("results", [])
    if not tracks:
        return None

    seen = recent_tracks.setdefault(chat_id, set())
    candidates = [t for t in tracks if t["id"] not in seen] or tracks

    track = random.choice(candidates)
    seen.add(track["id"])
    if len(seen) > 15:  # حافظه تکرار رو محدود نگه دار
        seen.pop()

    return track


async def welcome_with_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    chat_id = update.effective_chat.id
    names = ", ".join(m.first_name for m in update.message.new_chat_members)

    track = fetch_random_track(chat_id)
    if not track:
        await context.bot.send_message(chat_id, f"خوش اومدی {names} 🎉")
        return

    caption = f"🎉 خوش اومدی {names}!\n🎵 {track['name']} — {track['artist_name']}"
    await context.bot.send_audio(
        chat_id=chat_id,
        audio=track["audio"],          # لینک استریم مستقیم و قانونی
        title=track["name"],
        performer=track["artist_name"],
        caption=caption,
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_with_music))
    log.info("Party bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
