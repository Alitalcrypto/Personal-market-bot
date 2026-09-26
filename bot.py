"""Standalone, read-only personal market Telegram bot."""
import argparse
import base64
import csv
import io
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
OWNER = int(os.getenv("OWNER_ID", "0"))
DB = os.getenv("DATABASE_PATH", "market_bot.sqlite3")
REPORT_TIME = os.getenv("REPORT_TIME", "16:30")
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
TEHRAN = ZoneInfo("Asia/Tehran")
PERSONAL = "BTC ETH SOL BNB ADA XRP DOGE SUI LINK GRAM ZEC AAVE".split()
STABLE = {"USDT", "USDC", "DAI", "FDUSD", "USDE", "TUSD", "PYUSD", "USDD", "RLUSD"}
STOCKS = ["وبملت", "وتجارت"]
METALS = ["XAU-USD", "XAG-USD", "XAU-IRR", "XAG-IRR", "USD-IRR"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "StandalonePersonalMarketBot/1.0"})


def conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return c


def state_get(key, default=""):
    with conn() as c:
        row = c.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def state_set(key, value):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, str(value)))


def api(method, *, files=None, **params):
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN missing")
    r = SESSION.post(f"https://api.telegram.org/bot{TOKEN}/{method}",
                     data=params, files=files, timeout=TIMEOUT + 25)
    r.raise_for_status()
    result = r.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method}: {result.get('description')}")
    return result["result"]


def send(message, chat=None):
    chat = OWNER if chat is None else chat
    for start in range(0, len(message), 3500):
        api("sendMessage", chat_id=chat, text=message[start:start + 3500])


def get_json(url, params):
    r = SESSION.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def top50():
    data = get_json("https://api.coingecko.com/api/v3/coins/markets", {
        "vs_currency": "usd", "order": "market_cap_desc", "per_page": 50,
        "page": 1, "sparkline": "false"})
    if not isinstance(data, list) or len(data) < 40:
        raise ValueError("incomplete CoinGecko response")
    return data[:50]


def candles(symbol):
    if symbol in METALS or symbol in STOCKS:
        path = Path("data") / f"{symbol}.csv"
        if not path.is_file():
            raise ValueError("فایل داده موجود نیست")
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        parsed = []
        for row in rows:
            day = datetime.strptime(row["date"], "%Y-%m-%d").date()
            o, h, l, v = (float(row[k]) for k in ("open", "high", "low", "close"))
            if min(o, h, l, v) <= 0 or not l <= min(o, v) <= max(o, v) <= h:
                raise ValueError("OHLC نامعتبر")
            parsed.append((day, v))
        parsed.sort(key=lambda x: x[0])
        if len({d for d, _ in parsed}) != len(parsed):
            raise ValueError("تاریخ تکراری")
    else:
        if not re.fullmatch(r"[A-Z0-9]{2,15}", symbol):
            raise ValueError("نماد نامعتبر")
        data = get_json("https://api.binance.com/api/v3/klines",
                        {"symbol": symbol + "USDT", "interval": "1d", "limit": 120})
        today_utc = datetime.now(timezone.utc).date()
        parsed = [(datetime.fromtimestamp(x[0] / 1000, timezone.utc).date(), float(x[4]))
                  for x in data if datetime.fromtimestamp(x[0] / 1000, timezone.utc).date() < today_utc]
    if len(parsed) < 55:
        raise ValueError("کمتر از ۵۵ کندل کامل")
    latest = parsed[-1][0]
    if (datetime.now(TEHRAN).date() - latest).days > 4:
        raise ValueError(f"داده قدیمی: {latest}")
    return parsed


def ema(values, n):
    avg = sum(values[:n]) / n
    for x in values[n:]:
        avg += (x - avg) * 2 / (n + 1)
    return avg


def rsi(values, n=14):
    changes = [b - a for a, b in zip(values[-n-1:-1], values[-n:])]
    up = sum(max(x, 0) for x in changes) / n
    down = sum(max(-x, 0) for x in changes) / n
    return 100 if down == 0 else 100 - 100 / (1 + up / down)


def assess(symbol, series):
    close = [v for _, v in series]
    price, fast, slow, momentum = close[-1], ema(close, 20), ema(close, 50), rsi(close)
    if price > fast > slow and 50 <= momentum <= 70:
        label = "خرید مشروط"
        stop = min(close[-20:])
        if stop >= price:
            label = "انتظار"
            target = None
        else:
            target = price + 2 * (price - stop)
    elif price < fast < slow and momentum < 45:
        label, stop, target = "فروش/کاهش ریسک", None, None
    else:
        label, stop, target = "انتظار", None, None
    return {"symbol": symbol, "price": price, "ema20": fast, "ema50": slow,
            "rsi": momentum, "signal": label, "stop": stop, "target": target,
            "date": str(series[-1][0])}


def fmt(a):
    s = f"{a['symbol']}: {a['signal']} | {a['price']:,.6g} | RSI {a['rsi']:.1f} | {a['date']}"
    if a["stop"] is not None:
        s += f" | حدضرر {a['stop']:,.6g} | هدف {a['target']:,.6g}"
    return s


def report():
    now = datetime.now(TEHRAN).strftime("%Y-%m-%d %H:%M")
    lines = [f"گزارش مستقل بازار | تهران {now}", "قانون: EMA20/50 + RSI14؛ فقط کندل بسته و داده تازه."]
    try:
        coins = top50()
        symbols = list(dict.fromkeys([str(c["symbol"]).upper() for c in coins] + PERSONAL))
        lines.append("۵۰ رمزارز برتر بر پایه ارزش بازار؛ سپس رمزارزهای شخصی:")
    except Exception as e:
        coins = []
        symbols = PERSONAL[:]
        lines.append(f"فهرست ۵۰ ارز در دسترس نیست ({type(e).__name__})؛ فقط فهرست شخصی بررسی شد.")
    results = []
    for symbol in symbols + METALS + STOCKS:
        if symbol in STABLE:
            results.append(f"{symbol}: ارز باثبات؛ سیگنال روند صادر نمی‌شود")
            continue
        try:
            results.append(fmt(assess(symbol, candles(symbol))))
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            results.append(f"{symbol}: داده ناکافی ({str(e)[:65]})")
        time.sleep(0.12)
    lines.extend(results)
    lines.append("قیمت‌های USD، USDT و ریال جداگانه‌اند. سیگنال الگوریتمی است و توصیه شخصی نیست.")
    return "\n".join(lines)


def chart(symbol):
    series = candles(symbol)
    dates = [x[0] for x in series[-90:]]
    values = [x[1] for x in series[-90:]]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.plot(dates, values, label="Daily close")
    ax.set(title=f"{symbol} | daily close | through {dates[-1]}", ylabel="IRR" if symbol.endswith("IRR") or symbol in STOCKS else "USD/USDT")
    ax.grid(alpha=.25)
    ax.legend()
    fig.autofmt_xdate()
    img = io.BytesIO()
    fig.savefig(img, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    img.seek(0)
    return img


def send_report():
    send(report())
    try:
        api("sendPhoto", chat_id=OWNER, caption="نمودار روزانه BTC؛ کندل‌های بسته",
            files={"photo": ("BTC.png", chart("BTC"), "image/png")})
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        send("نمودار امروز در دسترس نیست: " + str(e)[:100])


def persist_snapshot(body, png):
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required for scheduled run")
    payload = {"report_day": datetime.now(TEHRAN).date().isoformat(),
               "body": body, "chart_base64": base64.b64encode(png).decode() if png else None}
    response = SESSION.post(url + "/rest/v1/market_reports?on_conflict=report_day",
        headers={"apikey": key, "Authorization": "Bearer " + key,
                 "Prefer": "resolution=merge-duplicates,return=minimal"},
        json=payload, timeout=TIMEOUT + 15)
    response.raise_for_status()


def handle(update):
    message = update.get("message", {})
    chat = message.get("chat", {})
    user = message.get("from", {})
    cmd = (message.get("text") or "").strip().split()
    if chat.get("type") != "private" or user.get("is_bot") or not cmd:
        return
    chat_id = chat.get("id")
    if cmd[0].split("@")[0] == "/id":
        send(f"شناسه گفت‌وگو: {chat_id}", chat_id)
        return
    if not OWNER or user.get("id") != OWNER or chat_id != OWNER:
        return
    action = cmd[0].split("@")[0].lower()
    if action in ("/start", "/help"):
        send("/report /signal BTC /chart BTC /watch /status /id")
    elif action == "/watch":
        send("ارزهای شخصی: " + ", ".join(PERSONAL) + "\nبورس: " + ", ".join(STOCKS) + "\nفلزات: " + ", ".join(METALS))
    elif action == "/status":
        send("آخرین گزارش: " + state_get("last_report", "هنوز ارسال نشده") + "\nفایل‌های بازار ایران: " + ", ".join(p.name for p in Path("data").glob("*.csv")))
    elif action == "/report":
        send_report()
    elif action in ("/signal", "/chart") and len(cmd) == 2:
        symbol = cmd[1].upper() if cmd[1] not in STOCKS else cmd[1]
        if symbol in STABLE:
            send("برای ارز باثبات سیگنال روند صادر نمی‌شود.")
            return
        if symbol not in PERSONAL + STOCKS + METALS:
            try:
                if symbol not in [str(c["symbol"]).upper() for c in top50()]:
                    send("نماد خارج از فهرست شخصی و ۵۰ ارز برتر است.")
                    return
            except requests.RequestException:
                send("فهرست ۵۰ ارز اکنون قابل بررسی نیست.")
                return
        try:
            if action == "/signal":
                send(fmt(assess(symbol, candles(symbol))))
            else:
                api("sendPhoto", chat_id=OWNER, caption=f"نمودار {symbol}", files={"photo": (f"{symbol}.png", chart(symbol), "image/png")})
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            send("داده کافی برای تحلیل نیست: " + str(e)[:120])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not TOKEN:
        raise SystemExit("Set BOT_TOKEN in .env")
    if args.once:
        if not OWNER:
            raise SystemExit("Set OWNER_ID before sending reports")
        body = report()
        try:
            png = chart("BTC").getvalue()
        except (requests.RequestException, ValueError, KeyError, IndexError):
            png = None
        if os.getenv("SUPABASE_URL"):
            persist_snapshot(body, png)
        send(body)
        if png:
            api("sendPhoto", chat_id=OWNER, caption="نمودار روزانه BTC؛ کندل‌های بسته",
                files={"photo": ("BTC.png", io.BytesIO(png), "image/png")})
        state_set("last_report", datetime.now(TEHRAN).isoformat())
        return
    while True:
        try:
            offset = int(state_get("offset", "0"))
            for update in api("getUpdates", offset=offset, timeout=20, allowed_updates='["message"]'):
                offset = update["update_id"] + 1
                try:
                    handle(update)
                except Exception as e:
                    print("Message error:", type(e).__name__, str(e)[:150], flush=True)
                state_set("offset", offset)
            now = datetime.now(TEHRAN)
            day = now.date().isoformat()
            if OWNER and now.strftime("%H:%M") >= REPORT_TIME and state_get("report_day") != day:
                send_report()
                state_set("report_day", day)
                state_set("last_report", now.isoformat())
        except (requests.RequestException, RuntimeError, ValueError) as e:
            print("Loop error:", type(e).__name__, str(e)[:150], flush=True)
            time.sleep(20)


if __name__ == "__main__":
    main()
