# بات مستقل پایش بازار

این پروژه مستقل از ATLAS است و هیچ شناسه، پایگاه داده، وب‌هوک یا توکنی از آن استفاده نمی‌کند. تحلیل‌ها بر مبنای کندل روزانه و قوانین شفاف EMA20/EMA50 و RSI14 تولید می‌شوند؛ سفارش واقعی ثبت نمی‌شود.

## معماری GitHub + Supabase

مخزن مستقل **Public** GitHub `Alitalcrypto/Personal-market-bot` مقصد این پروژه است. هر روز ساعت ۱۶:۳۰ تهران تحلیل را اجرا می‌کند، متن و نمودار BTC را در پروژه مستقل Supabase ذخیره و برای مالک در تلگرام ارسال می‌کند. تابع `market-webhook` در Supabase به فرمان‌های تلگرام پاسخ می‌دهد و آخرین گزارش ذخیره‌شده را می‌خواند. جریان تلگرام با webhook کار می‌کند؛ برنامه polling هم‌زمان نباید اجرا شود.

ترتیب راه‌اندازی:

1. یک پروژه Supabase مستقل بسازید، SQL فایل `supabase/schema.sql` را اجرا کنید.
2. اسرار تابع Supabase را تنظیم کنید: `BOT_TOKEN`، `OWNER_ID=414890497`، `WEBHOOK_SECRET`، `SUPABASE_URL` و `SUPABASE_SERVICE_ROLE_KEY`.
3. تابع `supabase/functions/market-webhook/index.ts` را با **verify_jwt=false** منتشر کنید.
4. Secrets مخزن GitHub: `BOT_TOKEN`، `OWNER_ID`، `SUPABASE_URL`، `SUPABASE_SERVICE_ROLE_KEY`. کلید service role فقط در اسرار سرور و GitHub Actions قرار می‌گیرد.
5. یک بار `workflow_dispatch` را اجرا کنید؛ سپس webhook را با `setWebhook` به نشانی تابع وصل کنید و `secret_token` را برابر `WEBHOOK_SECRET` بگذارید.

در این بسته هیچ توکن یا کلید خصوصی قرار ندارد. سیگنال‌ها قاعده‌ای و آموزشی هستند و سفارش واقعی ثبت نمی‌شود.

## راه‌اندازی

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py --once
python bot.py
```

## فرمان‌ها

`/report`، `/signal BTC`، `/chart BTC`، `/watch`، `/status`.

برای بورس ایران و فلزات، CSVهای معتبر را در `data/` قرار دهید. قالب `date,open,high,low,close,volume` و حداقل ۵۵ روز معاملاتی است.
