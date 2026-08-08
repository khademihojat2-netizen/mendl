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
- فیلتر ناسزا و اسپم: تا ۳ اخطار، بعدش بلاک خودکار
  - لایه سریع: لیست ثابت BAD_WORDS + regex تشخیص لینک
  - لایه هوشمند: طبقه‌بندی با هوش مصنوعی (Groq API - رایگان، نیاز به GROQ_API_KEY)
    تشخیص می‌ده پیام ناسزاست، اسپم/تبلیغ/لینک مشکوکه، یا عادیه
- هندلر خطا تا کرش نکنه اگه یه درخواست به تلگرام fail بشه
- وب‌سرور واسطه (Flask) برای پروکسی درخواست موزیک به Jamendo، تا اگه
  Jamendo از سمت کاربر فیلتر بود، مشکلی برای پیدا کردن آهنگ پیش نیاد
- چت‌بات هوشمند: با منشن کردن بات (@) یا ریپلای به پیامش، سوال بپرس
  و با Groq جواب می‌گیری
- خوش‌آمدگویی شخصی‌سازی‌شده: هر عضو جدید یه پیام خوش‌آمد متفاوت و
  بامزه با AI می‌گیره (نه یه متن ثابت تکراری)
- بازی تریویا: با /trivia یه سوال موزیک/پارتی می‌سازه، اولین جواب درست می‌بره

نصب:
    pip install python-telegram-bot==21.4 requests flask

اجرا:
    python party_bot.py
"""

import os
import re
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
trivia_state = {}  # chat_id -> {"answer": str, "score": {user_id: count}}

# ⚠️ لیست کلمات ناسزا/فحش رو خودت اینجا پر کن (حروف کوچیک، بدون فاصله اضافه).
# مثال: BAD_WORDS = ["کلمه۱", "کلمه۲", "کلمه۳"]
BAD_WORDS = []

MAX_WARNINGS = 3

# لینک/دعوت گروه/کانال -> لایه‌ی سریع تشخیص اسپم (بدون نیاز به AI)
LINK_REGEX = re.compile(r"(https?://\S+|t\.me/\S+|@\w{4,}\b)", re.IGNORECASE)

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


async def trivia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """یه سوال تریویا/موزیک با AI می‌سازه؛ اولین نفری که درست جواب بده می‌بره."""
    chat_id = update.effective_chat.id

    if not GROQ_API_KEY:
        await update.message.reply_text("این قابلیت نیاز به GROQ_API_KEY داره که هنوز ست نشده.")
        return

    reply = await ask_groq(
        "یه سوال تریویای سرگرم‌کننده درباره‌ی موزیک، خواننده‌ها، یا فرهنگ پاپ/پارتی بساز "
        "(سطح متوسط، نه خیلی سخت نه خیلی ساده). دقیقاً با همین فرمت جواب بده و هیچ چیز دیگه‌ای ننویس:\n"
        "سوال: <متن سوال>\n"
        "جواب: <جواب کوتاه، یک یا چند کلمه>",
        "یه سوال تریویای جدید بساز",
        max_tokens=150,
    )
    if not reply:
        await update.message.reply_text("نتونستم سوال بسازم، دوباره امتحان کن.")
        return

    q_match = re.search(r"سوال:\s*(.+)", reply)
    a_match = re.search(r"جواب:\s*(.+)", reply)
    if not q_match or not a_match:
        await update.message.reply_text("نتونستم سوال بسازم، دوباره امتحان کن.")
        return

    question = q_match.group(1).strip()
    answer = a_match.group(1).strip()

    trivia_state[chat_id] = {"answer": answer.lower()}
    await update.message.reply_text(f"🎮 سوال تریویا:\n\n{question}\n\nاولین نفری که درست جواب بده می‌بره! 🏆")


async def trivia_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اگه یه سوال تریویا فعاله، جواب کاربر رو چک می‌کنه."""
    chat_id = update.effective_chat.id
    state = trivia_state.get(chat_id)
    if not state or not update.message or not update.message.text:
        return

    guess = update.message.text.strip().lower()
    correct_answer = state["answer"]

    # تطبیق ساده: جواب دقیق یا وقتی جواب درست داخل پیام کاربر باشه
    if guess == correct_answer or correct_answer in guess:
        user = update.effective_user
        del trivia_state[chat_id]
        await update.message.reply_text(
            f"🎉 آفرین {user.first_name}! جواب درست بود: «{state['answer']}» — تو بردی! 🏆"
        )


async def welcome_with_party_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    chat_id = update.effective_chat.id
    members = update.message.new_chat_members
    names = ", ".join(m.first_name for m in members)
    party_count[chat_id] = party_count.get(chat_id, 0) + 1

    text = None
    if GROQ_API_KEY:
        text = await ask_groq(
            "تو دستیار یه بات پارتی توی تلگرام هستی. یه پیام خوش‌آمدگویی کوتاه "
            "(یک جمله، حداکثر ۲۰ کلمه)، شاد و بامزه به فارسی برای عضو جدید گروه بنویس. "
            "حتماً اسمی که بهت میدم رو توش بیار. از ایموجی مرتبط با پارتی استفاده کن. "
            "فقط خودِ پیام رو بنویس، بدون توضیح اضافه.",
            f"اسم عضو جدید: {names}",
            max_tokens=60,
        )

    if not text:
        text = f"خوش اومدی {names}! برای شروع موزیک و نورهای پارتی دکمه زیر رو بزن 👇"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
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
        "• /trivia — یه بازی تریویای موزیک/پارتی شروع کن\n"
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


async def ai_classify_message(text: str, has_link: bool) -> str | None:
    """پیام رو با Groq طبقه‌بندی می‌کنه: 'ناسزا'، 'اسپم'، یا 'خیر'.
    فقط وقتی GROQ_API_KEY ست شده باشه فعاله."""
    hint = " (این پیام یه لینک/منشن هم داره)" if has_link else ""
    reply = await ask_groq(
        "تو یه فیلتر مدیریت گروه تلگرام هستی. پیام کاربر رو بخون و فقط با یکی از "
        "این سه کلمه جواب بده (بدون هیچ توضیح اضافه):\n"
        "'ناسزا' اگه پیام فحش/توهین/کلمات رکیک داشت (حتی با غلط‌املایی عمدی)\n"
        "'اسپم' اگه پیام تبلیغ، لینک مشکوک/فروش/کانال ناشناس، یا دعوت اسپم‌طور بود\n"
        "'خیر' اگه پیام عادی، دوستانه، یا لینک بی‌ضرر (مثل عکس/آهنگ/جواب به بحث گروه) بود",
        text + hint,
        max_tokens=5,
    )
    if not reply:
        return None
    if reply.startswith("ناسزا"):
        return "ناسزا"
    if reply.startswith("اسپم"):
        return "اسپم"
    return None


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
    """هر پیام متنی گروه رو چک می‌کنه؛ اگه ناسزا یا اسپم/لینک مشکوک بود، اخطار میده
    و بعد ۳ اخطار بلاک می‌کنه.
    لایه سریع: لیست BAD_WORDS + regex لینک. لایه هوشمند: طبقه‌بندی با Groq.
    نیازمند اینه که بات توی گروه ادمین باشه با دسترسی 'Ban users' و 'Delete messages'."""
    if not update.message or not update.message.text:
        return

    text = update.message.text
    text_lower = text.lower()
    has_link = bool(LINK_REGEX.search(text))

    reason = None
    if BAD_WORDS and any(bad in text_lower for bad in BAD_WORDS):
        reason = "ناسزا"
    else:
        reason = await ai_classify_message(text, has_link)

    if not reason:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    key = (chat_id, user.id)
    warnings[key] = warnings.get(key, 0) + 1
    count = warnings[key]

    # پیام حاوی ناسزا/اسپم رو حذف کن (اگه بات دسترسی حذف پیام داشته باشه)
    try:
        await update.message.delete()
    except TelegramError:
        pass

    reason_text = "لطفاً درست صحبت کن" if reason == "ناسزا" else "لینک/تبلیغ اینجا مجاز نیست"

    if count < MAX_WARNINGS:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {user.first_name} عزیز، {reason_text}. اخطار {count} از {MAX_WARNINGS}.",
        )
    else:
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚫 {user.first_name} به‌خاطر تکرار {reason} از گروه بلاک شد.",
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
        BotCommand("trivia", "شروع یه بازی تریویای موزیک/پارتی"),
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
    app.add_handler(CommandHandler("trivia", trivia_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_with_party_button))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderate_message), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_reply), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, trivia_check), group=2)
    app.add_error_handler(error_handler)

    log.info("Party bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
