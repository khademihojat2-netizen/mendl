"""
Party Bot - وقتی کسی وارد گروه تلگرام میشه (یا با دستور /party)، دکمه Mini App
پارتی رو میفرسته. با باز شدن Mini App، صفحه خودش یه آهنگ رندوم از Jamendo
(قانونی/Royalty-free) میگیره و بلافاصله پخش میکنه + نورهای پارتی روشن میشه.

قابلیت‌ها:
- خوش‌آمد خودکار به اعضای جدید با دکمه ورود به مهمونی
- دستور دستی /party برای شروع مهمونی هر موقع که بخوای
  - /party تولد  -> تم تولد
  - /party سال_نو -> تم سال نو
  - /party (بدون آرگومان) -> تم پیش‌فرض
- پیام خداحافظی وقتی کسی گروه رو ترک می‌کنه
- شمارنده‌ی تعداد دفعاتی که مهمونی شروع شده (در حافظه)
- فیلتر ناسزا: تا ۳ اخطار، بعدش بلاک خودکار
  - لایه سریع: لیست ثابت BAD_WORDS
  - لایه هوشمند: تشخیص با هوش مصنوعی (Groq API - رایگان، نیاز به GROQ_API_KEY)
- هندلر خطا تا کرش نکنه اگه یه درخواست به تلگرام fail بشه
- وب‌سرور واسطه (Flask) برای پروکسی درخواست موزیک به Jamendo، تا اگه
  Jamendo از سمت کاربر فیلتر بود، مشکلی برای پیدا کردن آهنگ پیش نیاد
- چت‌بات هوشمند: با منشن کردن بات (@) یا ریپلای به پیامش، سوال بپرس
  و با Groq جواب می‌گیری

نصب:
    pip install python-telegram-bot==21.4 requests flask

اجرا:
    python party_bot.py
"""

import os
import logging
import asyncio
import threading
import requests
from flask import Flask, jsonify, request as flask_request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.error import TelegramError
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

# کلید API گروک (Groq - سریع و دارای تیر کاملاً رایگان، بدون کارت بانکی).
# از console.groq.com بگیر و توی Railway به‌عنوان GROQ_API_KEY ست کن.
# اگه ست نشه، فقط از لیست ثابت BAD_WORDS استفاده می‌شه (بدون هوش مصنوعی).
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("party_bot")

party_count = {}  # chat_id -> تعداد دفعات شروع مهمونی
warnings = {}  # (chat_id, user_id) -> تعداد اخطارها

# ⚠️ لیست کلمات ناسزا/فحش رو خودت اینجا پر کن (حروف کوچیک، بدون فاصله اضافه).
# مثال: BAD_WORDS = ["کلمه۱", "کلمه۲", "کلمه۳"]
BAD_WORDS = []

MAX_WARNINGS = 3

# کلیدواژه‌ای که کاربر بعد از /party می‌نویسه -> کد تم (start_param)
OCCASIONS = {
    "تولد": "birthday",
    "سال_نو": "newyear",
    "سال نو": "newyear",
    "کریسمس": "christmas",
}


JAMENDO_CLIENT_ID = "b0cd7e21"
MAX_TRACK_DURATION = 240
DEFAULT_TAGS = "party+dance+electronic"


def party_button(occasion_code: str | None = None):
    url = MINI_APP_DEEPLINK
    if occasion_code:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}startapp={occasion_code}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ورود به مهمونی 🎉", url=url)]
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
    """
    دستور دستی /party [مناسبت]
    مثال: /party تولد   یا   /party سال_نو   یا فقط /party
    """
    chat_id = update.effective_chat.id
    party_count[chat_id] = party_count.get(chat_id, 0) + 1

    occasion_text = " ".join(context.args) if context.args else None
    occasion_code = OCCASIONS.get(occasion_text) if occasion_text else None

    if occasion_text and not occasion_code:
        known = "، ".join(sorted(set(OCCASIONS.keys())))
        await update.message.reply_text(f"این مناسبت رو نمی‌شناسم. گزینه‌های موجود: {known}")
        return

    label = f"مهمونی {occasion_text} شروع شد! 🎊" if occasion_text else "مهمونی شروع شد! 🎊"
    await update.message.reply_text(
        f"{label} دکمه زیرو بزن:",
        reply_markup=party_button(occasion_code),
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    count = party_count.get(chat_id, 0)
    await update.message.reply_text(f"🎉 تا الان {count} بار مهمونی توی این گروه شروع شده!")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    known = "\n".join(f"• /party {name}" for name in sorted(set(OCCASIONS.keys())))
    text = (
        "🎉 راهنمای بات پارتی 🎉\n\n"
        "دستورهای موجود:\n"
        "• /party — شروع مهمونی با تم معمولی\n"
        f"{known}\n"
        "• /partystats — تعداد دفعاتی که مهمونی توی این گروه شروع شده\n"
        "• /help — همین راهنما\n\n"
        "هر عضو گروه می‌تونه این دستورها رو بزنه، محدودیتی نداره."
    )
    await update.message.reply_text(text)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! برای ورود به مهمونی دکمه زیر رو بزن 👇\n"
        "برای دیدن همه‌ی دستورها /help رو بزن.",
        reply_markup=party_button(),
    )


async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("خطا هنگام پردازش یه آپدیت: %s", context.error, exc_info=context.error)


async def ask_groq(system_prompt: str, user_text: str, max_tokens: int = 300) -> str | None:
    """یه فراخوانی عمومی به Groq؛ برای فیلتر ناسزا و چت‌بات هردو ازش استفاده می‌شه."""
    if not GROQ_API_KEY:
        return None

    def call_api():
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text[:1500]},
                    ],
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.error("خطا در تماس با Groq API: %s", e)
            return None

    return await asyncio.to_thread(call_api)


async def ai_is_offensive(text: str) -> bool:
    """پیام رو با Groq چک می‌کنه که ناسزا/توهین/فحش هست یا نه (فارسی یا هر زبان دیگه).
    فقط وقتی GROQ_API_KEY ست شده باشه فعاله."""
    reply = await ask_groq(
        "تو یه فیلتر تشخیص ناسزا/فحش/توهین هستی. فقط با یک کلمه جواب بده: "
        "'بله' اگه پیام حاوی فحش، ناسزا، توهین مستقیم به شخص، یا کلمات رکیک باشه "
        "(حتی با غلط‌املایی عمدی یا حروف انگلیسی برای نوشتن فارسی)، "
        "یا 'خیر' اگه پیام عادی و بی‌مشکل باشه.",
        text,
        max_tokens=5,
    )
    return bool(reply) and reply.startswith("بله")


async def ai_chat_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اگه کسی بات رو منشن (@) کنه یا روی پیام بات ریپلای بزنه، با Groq جواب می‌ده.
    فقط وقتی GROQ_API_KEY ست شده باشه فعاله."""
    if not GROQ_API_KEY or not update.message or not update.message.text:
        return

    bot_username = context.bot.username
    text = update.message.text
    mentioned = bot_username and f"@{bot_username}" in text
    is_reply_to_bot = (
        update.message.reply_to_message
        and update.message.reply_to_message.from_user
        and update.message.reply_to_message.from_user.id == context.bot.id
    )
    if not (mentioned or is_reply_to_bot):
        return

    question = text.replace(f"@{bot_username}", "").strip() if mentioned else text
    if not question:
        return

    reply = await ask_groq(
        "تو دستیار هوشمند یه بات پارتی توی تلگرام هستی، اسمت هم همینه. "
        "خودمونی، دوستانه و کوتاه (حداکثر ۲-۳ جمله) به فارسی جواب بده. "
        "اگه سوال درباره‌ی خود مهمونی/موزیک بود، می‌تونی به دستور /party هم اشاره کنی.",
        question,
    )
    if reply:
        await update.message.reply_text(reply)


async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هر پیام متنی گروه رو چک می‌کنه؛ اگه ناسزا/توهین بود، اخطار میده و بعد ۳ اخطار بلاک می‌کنه.
    اول لیست ثابت BAD_WORDS چک می‌شه (سریع)، اگه چیزی پیدا نشد و AI فعال باشه،
    از کلود برای تشخیص هوشمندتر (کنایه، غلط‌املایی عمدی، و...) استفاده می‌شه.
    نیازمند اینه که بات توی گروه ادمین باشه با دسترسی 'Ban users' و 'Delete messages'."""
    if not update.message or not update.message.text:
        return

    text_lower = update.message.text.lower()
    flagged = bool(BAD_WORDS) and any(bad in text_lower for bad in BAD_WORDS)

    if not flagged:
        flagged = await ai_is_offensive(update.message.text)

    if not flagged:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    key = (chat_id, user.id)
    warnings[key] = warnings.get(key, 0) + 1
    count = warnings[key]

    # پیام حاوی ناسزا رو حذف کن (اگه بات دسترسی حذف پیام داشته باشه)
    try:
        await update.message.delete()
    except TelegramError:
        pass

    if count < MAX_WARNINGS:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {user.first_name} عزیز، لطفاً درست صحبت کن. اخطار {count} از {MAX_WARNINGS}.",
        )
    else:
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚫 {user.first_name} به‌خاطر تکرار ناسزا از گروه بلاک شد.",
            )
        except TelegramError as e:
            log.error("نتونستم کاربر رو بلاک کنم (احتمالاً بات ادمین نیست): %s", e)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name} باید بلاک می‌شد ولی من دسترسی ادمین ندارم.",
            )
        finally:
            warnings.pop(key, None)


async def post_init(app):
    """لیست دستورها رو توی منوی خودکار تلگرام (وقتی / تایپ میشه) ثبت می‌کنه
    تا همه‌ی اعضای گروه بدون نیاز به پرسیدن، خودشون گزینه‌ها رو ببینن."""
    await app.bot.set_my_commands([
        BotCommand("party", "شروع مهمونی (مثال: /party تولد یا /party سال_نو)"),
        BotCommand("partystats", "تعداد دفعاتی که مهمونی شروع شده"),
        BotCommand("help", "راهنمای کامل دستورها و مناسبت‌ها"),
        BotCommand("start", "شروع کار با بات"),
    ])


# ---------------- وب‌سرور واسطه (پروکسی Jamendo) ----------------
# چون خیلی از پروکسی/فیلترشکن‌های تلگرام فقط ترافیک خود تلگرام رو رد می‌کنن،
# درخواست مستقیم Mini App به api.jamendo.com ممکنه فیلتر بشه. اینجا خودِ
# سرور Railway (که فیلتر نیست) واسطه‌ست: Mini App به همینجا درخواست می‌ده،
# اینجا از سمت سرور با Jamendo صحبت می‌کنه و جواب رو برمی‌گردونه.
flask_app = Flask(__name__)


@flask_app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@flask_app.route("/track", methods=["GET"])
def get_track():
    tags = flask_request.args.get("tags", DEFAULT_TAGS)
    try:
        resp = requests.get(
            "https://api.jamendo.com/v3.0/tracks/",
            params={
                "client_id": JAMENDO_CLIENT_ID,
                "format": "json",
                "limit": 40,
                "tags": tags,
                "durationbetween": f"30_{MAX_TRACK_DURATION}",
                "order": "popularity_total",
                "audioformat": "mp32",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except Exception as e:
        log.error("خطا هنگام گرفتن ترک از Jamendo: %s", e)
        return jsonify({"results": [], "error": str(e)}), 502


@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


def main():
    # وب‌سرور واسطه رو توی یه thread جدا بالا میاریم تا هم‌زمان با بات کار کنه
    threading.Thread(target=run_web_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("party", party_command))
    app.add_handler(CommandHandler("partystats", stats_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_with_party_button))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderate_message), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_reply), group=1)
    app.add_error_handler(error_handler)

    log.info("Party bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
