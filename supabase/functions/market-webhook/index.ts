// Telegram webhook: the Edge Function owns chat replies; GitHub owns analysis.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.95.0";

const botToken = Deno.env.get("BOT_TOKEN") ?? "";
const owner = Number(Deno.env.get("OWNER_ID") ?? "0");
const hookSecret = Deno.env.get("WEBHOOK_SECRET") ?? "";
const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const db = createClient(Deno.env.get("SUPABASE_URL") ?? "", serviceKey);
const personal = "BTC ETH SOL BNB ADA XRP DOGE SUI LINK GRAM ZEC AAVE";
const markets = "وبملت، وتجارت؛ XAU-USD، XAG-USD، XAU-IRR، XAG-IRR، USD-IRR";

async function telegram(method: string, body: object | FormData) {
  const response = await fetch(`https://api.telegram.org/bot${botToken}/${method}`, {
    method: "POST",
    ...(body instanceof FormData ? { body } : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  if (!response.ok || !(await response.json()).ok) throw new Error(`Telegram ${method} failed`);
}
async function message(chat_id: number, body: string) {
  for (let i = 0; i < body.length; i += 3500) {
    await telegram("sendMessage", { chat_id, text: body.slice(i, i + 3500) });
  }
}
async function latest() {
  const { data, error } = await db.from("market_reports")
    .select("report_day,body,chart_base64,created_at").order("report_day", { ascending: false }).limit(1).maybeSingle();
  if (error) throw error;
  return data;
}
async function sendChart(chatId: number, png: string) {
  const bytes = Uint8Array.from(atob(png), x => x.charCodeAt(0));
  const form = new FormData();
  form.set("chat_id", String(chatId));
  form.set("caption", "نمودار BTC در آخرین گزارش روزانه");
  form.set("photo", new Blob([bytes], { type: "image/png" }), "BTC.png");
  await telegram("sendPhoto", form);
}

Deno.serve(async req => {
  if (req.method !== "POST" || !hookSecret || !botToken || !owner || !serviceKey ||
      req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== hookSecret) {
    return new Response("unauthorized", { status: 401 });
  }
  try {
    const update = await req.json();
    const m = update?.message;
    if (!m || m.chat?.type !== "private" || m.chat?.id !== owner || m.from?.id !== owner) {
      return new Response("ok");
    }
    const [raw, arg] = String(m.text ?? "").trim().split(/\s+/, 2);
    const cmd = raw?.split("@")[0].toLowerCase();
    const chatId = owner;
    if (cmd === "/start" || cmd === "/help") {
      await message(chatId, "/report /signal BTC /chart BTC /watch /status");
    } else if (cmd === "/watch") {
      await message(chatId, `ارزهای شخصی: ${personal}\nبورس و فلزات: ${markets}`);
    } else if (["/report", "/signal", "/chart", "/status"].includes(cmd)) {
      const data = await latest();
      if (!data) { await message(chatId, "گزارش ذخیره‌شده هنوز موجود نیست."); return new Response("ok"); }
      if (cmd === "/status") await message(chatId, `آخرین گزارش: ${data.report_day}`);
      else if (cmd === "/report") {
        await message(chatId, data.body);
        if (data.chart_base64) await sendChart(chatId, data.chart_base64);
      } else if (cmd === "/signal") {
        const symbol = (arg ?? "").toUpperCase();
        const line = data.body.split("\n").find((x: string) => x.toUpperCase().startsWith(symbol + ":"));
        await message(chatId, symbol && line ? line : "نماد در آخرین گزارش یافت نشد.");
      } else if (cmd === "/chart") {
        if ((arg ?? "").toUpperCase() === "BTC" && data.chart_base64) await sendChart(chatId, data.chart_base64);
        else await message(chatId, "در این نسخه فقط نمودار BTC در آخرین گزارش ذخیره شده است.");
      }
    }
    return new Response("ok");
  } catch (error) {
    console.error(error instanceof Error ? error.message : "unknown webhook error");
    return new Response("error", { status: 500 });
  }
});
