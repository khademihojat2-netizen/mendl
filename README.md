# tlmen-bot

نسخهٔ اصلاح‌شدهٔ تلگرام بات برای دانلود و ارسال ویدیو با yt-dlp.

## متغیرهای محیطی مورد نیاز
- BOT_TOKEN: توکن ربات تلگرام
- AUTHORIZED_USER: (اختیاری) شناسهٔ عددی تلگرام کاربر مجاز

## اجرا محلی
1. نصب وابستگی‌ها:
   pip install -r requirements.txt
2. تنظیم متغیرها (مثلاً در .env)
3. اجرا:
   python bot.py

## استقرار در Railway / Heroku
- متغیرهای محیطی را در بخش Variables تنظیم کنید.
- Procfile را اضافه کنید (`worker: python bot.py`).
- Builder را روی Python مناسب قرار دهید.
