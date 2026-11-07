import os
os.environ["PYTHONUNBUFFERED"] = "1"

import asyncio
import aiohttp
import json
import threading
import traceback
import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from supabase import create_client, Client

# ===== خواندن تنظیمات از متغیرهای محیطی =====
WC_URL = os.environ.get("WC_URL")
WC_KEY = os.environ.get("WC_KEY")
WC_SECRET = os.environ.get("WC_SECRET")

BALE_TOKEN = os.environ.get("BALE_TOKEN")
BALE_CHANNEL = os.environ.get("BALE_CHANNEL")
PRICE_JSON_URL = os.environ.get("PRICE_JSON_URL")

# ===== تنظیمات تلگرام =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ===== نام کاربری ربات‌ها =====
BALE_BOT_USERNAME = os.environ.get("BALE_BOT_USERNAME", "")
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ===== اتصال به Supabase =====
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# ===== وب‌سرور =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Behzadgold Bot is running."

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ===== توابع ثبت آمار =====
def log_user_stats(user_id, username, first_name):
    if not supabase: return
    try:
        res = supabase.table("bot_users").select("user_id, request_count").eq("user_id", user_id).execute()
        if res.data:
            current_count = res.data[0]["request_count"]
            supabase.table("bot_users").update({"request_count": current_count + 1, "last_request": "now()"}).eq("user_id", user_id).execute()
        else:
            supabase.table("bot_users").insert({"user_id": user_id, "username": username, "first_name": first_name, "request_count": 1}).execute()
    except Exception as e:
        print(f"❌ [DB] خطا در ثبت آمار: {e}")

def get_sent_history():
    if not supabase: return set()
    try:
        response = supabase.table("last_orders").select("sent_history").eq("site_name", "behzadgold_bot_sent_history").execute()
        if response.data and response.data[0].get("sent_history"):
            return set(json.loads(str(response.data[0]["sent_history"])))
        return set()
    except:
        return set()

def save_sent_history(history_set):
    if not supabase: return
    try:
        history_str = json.dumps(list(history_set))
        supabase.table("last_orders").update({"sent_history": history_str}).eq("site_name", "behzadgold_bot_sent_history").execute()
    except:
        pass

def get_out_of_stock():
    if not supabase: return set()
    try:
        response = supabase.table("last_orders").select("sent_history").eq("site_name", "behzadgold_bot_out_of_stock").execute()
        if response.data and response.data[0].get("sent_history"):
            return set(json.loads(str(response.data[0]["sent_history"])))
        return set()
    except:
        return set()

def save_out_of_stock(out_set):
    if not supabase: return
    try:
        history_str = json.dumps(list(out_set))
        supabase.table("last_orders").update({"sent_history": history_str}).eq("site_name", "behzadgold_bot_out_of_stock").execute()
    except:
        pass

# ===== ارسال به بله =====
async def send_to_bale(chat_id, text, photo_url=None, reply_markup=None, title=""):
    base_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
    data = {"chat_id": chat_id}
    if photo_url:
        data["photo"] = photo_url
        data["caption"] = text
        url = f"{base_url}/sendPhoto"
    else:
        data["text"] = text
        url = f"{base_url}/sendMessage"
    if reply_markup: 
        data["reply_markup"] = reply_markup

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=20) as resp:
                    if resp.status == 200:
                        print(f"✅ {title} به بله ارسال شد.")
                        return True
                    else:
                        print(f"❌ خطا در ارسال {title} به بله ({resp.status}) - تلاش مجدد...")
        except Exception as e:
            print(f"❌ خطای شبکه در ارسال {title} به بله ({e}) - تلاش مجدد...")
        
        await asyncio.sleep(5)

# ===== ارسال به تلگرام =====
async def send_to_telegram(chat_id, text, photo_url=None, reply_markup=None, title=""):
    if not TELEGRAM_TOKEN or not chat_id:
        print("⚠️ [TELEGRAM] توکن یا Chat ID تنظیم نشده است.")
        return False
    
    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    
    if photo_url:
        url = f"{base_url}/sendPhoto"
        data = {"chat_id": chat_id, "photo": photo_url, "caption": text, "parse_mode": "Markdown"}
    else:
        url = f"{base_url}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    
    if reply_markup:
        data["reply_markup"] = reply_markup

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=20) as resp:
                    if resp.status == 200:
                        print(f"✅ {title} به تلگرام ارسال شد.")
                        return True
                    else:
                        err = await resp.text()
                        if "can't parse entities" in err and "parse_mode" in data:
                            del data["parse_mode"]
                            print(f"⚠️ خطای فرمت بندی تلگرام. تلاش بدون فرمت...")
                            continue
                        print(f"❌ خطا در ارسال {title} به تلگرام ({resp.status}) - تلاش مجدد...")
        except Exception as e:
            print(f"❌ خطای شبکه در ارسال {title} به تلگرام ({e}) - تلاش مجدد...")
        
        await asyncio.sleep(5)

# ===== قیمت طلا =====
async def get_gold_price_text():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PRICE_JSON_URL, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return (
                        f"📊 *قیمت لحظه‌ای طلا و سکه*\n\n"
                        f"🔹 هر گرم طلای ۱۸ عیار: *{data.get('Geram18', '—')}* تومان\n"
                        f"🔹 هر گرم طلای آب شده: *{data.get('ForushAbshode', '—')}* تومان\n\n"
                        f"🟠 سکه امامی جدید: *{data.get('Tamam', '—')}* تومان\n"
                        f"🟠 سکه نیم بهار آزادی: *{data.get('Nim', '—')}* تومان\n"
                        f"🟠 سکه ربع بهار آزادی: *{data.get('Rob', '—')}* تومان\n"
                        f"🟠 سکه تمام طرح قدیم: *{data.get('SekeGhadim', '—')}* تومان\n\n"
                        f"🌍 اونس جهانی طلا: *{data.get('Ons', '—')}* دلار\n\n"
                        f"📅 تاریخ: {data.get('Date', '—')} - {data.get('Time', '—')}"
                    )
    except Exception as e:
        print(f"❌ خطا در دریافت قیمت: {e}")
    return "❌ خطا در دریافت قیمت طلا."

async def send_gold_price():
    # جلوگیری از ارسال در ساعت 00:30
    now = datetime.now(pytz.timezone('Asia/Tehran'))
    if now.hour == 0 and now.minute == 30:
        print("⏳ [JOB] ساعت ۰۰:۳۰ بامداد است. از ارسال قیمت صرف‌نظر شد.")
        return

    text = await get_gold_price_text()
    
    bale_btns = [[{"text": "🤖 دریافت قیمت لحظه‌ای از ربات", "url": f"https://ble.ir/{BALE_BOT_USERNAME}"}]] if BALE_BOT_USERNAME else None
    bale_markup = {"inline_keyboard": bale_btns} if bale_btns else None
    
    tg_btns = [[{"text": "🤖 دریافت قیمت لحظه‌ای از ربات", "url": f"https://t.me/{TELEGRAM_BOT_USERNAME}"}]] if TELEGRAM_BOT_USERNAME else None
    tg_markup = {"inline_keyboard": tg_btns} if tg_btns else None

    await send_to_bale(BALE_CHANNEL, text, reply_markup=bale_markup, title="قیمت طلا")
    await send_to_telegram(TELEGRAM_CHAT_ID, text, reply_markup=tg_markup, title="قیمت طلا")

# ===== محصولات =====
async def fetch_products(params):
    url = f"{WC_URL}/wp-json/wc/v3/products"
    final_params = {"consumer_key": WC_KEY, "consumer_secret": WC_SECRET}
    final_params.update(params)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=final_params, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200: return await resp.json()
    except:
        pass
    return []

async def fetch_variations(product_id):
    url = f"{WC_URL}/wp-json/wc/v3/products/{product_id}/variations"
    params = {"per_page": 100, "consumer_key": WC_KEY, "consumer_secret": WC_SECRET}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200: return await resp.json()
    except:
        pass
    return []

async def format_and_send_product(p):
    name = p.get("name", "بدون نام")
    price = p.get("price", "0")
    permalink = p.get("permalink", "")
    p_type = p.get("type", "simple")
    
    all_features = []
    weight_str = ""
    
    if p_type == "variable":
        variations = await fetch_variations(p["id"])
        weights = set()
        for v in variations:
            for attr in v.get("attributes", []):
                if attr.get("name") == "وزن" or attr.get("option"):
                    weights.add(attr.get("option"))
        if weights:
            weights_str = "، ".join(sorted(list(weights)))
            weight_str = f"⚖️ موجود در وزن‌های: {weights_str}"
    else:
        for attr in p.get("attributes", []):
            attr_name = attr.get("name", "")
            options = attr.get("options", [])
            
            if attr_name in ["عیار", "اجرت"]:
                continue
                
            if options and attr_name not in ("وزن",):
                all_features.append(f"🔹 {attr_name}: {options[0]}")
            elif options and attr_name == "وزن":
                weight_str = f"⚖️ وزن: {options[0]}"

    gold_price = "—"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PRICE_JSON_URL, headers=HEADERS, timeout=10) as resp:
                if resp.status == 200:
                    g_data = await resp.json()
                    gold_price = g_data.get("Geram18", "—")
    except:
        pass

    text = f"✨ *{name}* ✨\n\n"
    if weight_str:
        text += f"*{weight_str}*\n\n"
    text += "✅ فروش با فاکتور رسمی\n✅ امکان خرید در 4 قسط با اسنپ‌پی\n✅ تخفیف 12 درصدی برای خرید نقدی\n\n"
    if all_features:
        text += "📋 *مشخصات:*\n" + "\n".join(all_features) + "\n\n"
        
    text += f"💰 قیمت: {price} تومان\n📈 (این قیمت با طلای {gold_price} تومان محاسبه شده است)\n\n"
    text += (
        f"🏢 *آدرس فروشگاه:*\n"
        f"ساوه، خیابان سوم شعبان، پاساژ سامان، پلاک ۸\n"
        f"☎️ تلفن : 42226350 (086)\n\n"
        f"🔗 [مشاهده محصول در سایت]({permalink})"
    )

    images = p.get("images", [])
    photo_url = images[0]["src"] if images else None

    title = f"محصول {name}"
    await send_to_bale(BALE_CHANNEL, text, photo_url=photo_url, title=title)
    await send_to_telegram(TELEGRAM_CHAT_ID, text, photo_url=photo_url, title=title)
    
    return True

async def check_and_send_products():
    # جلوگیری از ارسال در ساعت 00:30
    now = datetime.now(pytz.timezone('Asia/Tehran'))
    if now.hour == 0 and now.minute == 30:
        print("⏳ [JOB] ساعت ۰۰:۳۰ بامداد است. از ارسال محصولات صرف‌نظر شد.")
        return

    # مکث ۳۰ ثانیه‌ای برای جلوگیری از تداخل با قیمت
    print("⏳ [JOB] مکث ۳۰ ثانیه‌ای برای جلوگیری از تداخل...")
    await asyncio.sleep(30)
    
    history = get_sent_history()
    out_of_stock = get_out_of_stock()

    all_products = []
    page = 1
    while True:
        batch = await fetch_products({"per_page": 100, "page": page, "orderby": "id", "order": "desc", "status": "publish"})
        if not batch:
            break
        all_products.extend(batch)
        page += 1
        if page > 20:
            break

    unsent = []
    for p in all_products:
        if p.get("status") != "publish":
            continue
        if p.get("stock_status") == "outofstock":
            out_of_stock.add(p["id"])
            continue
        if p["id"] in history:
            continue
        unsent.append(p)

    save_out_of_stock(out_of_stock)

    if not unsent:
        return

    selected_product = unsent[0]
    success = await format_and_send_product(selected_product)
    
    if success:
        history.add(selected_product["id"])
        save_sent_history(history)

async def check_out_of_stock():
    out_of_stock = get_out_of_stock()
    history = get_sent_history()
    if not out_of_stock: return

    for p_id in list(out_of_stock):
        p_data = await fetch_products({"include": p_id, "status": "publish"})
        if not p_data: continue
        p = p_data[0]
        if p.get("stock_status") != "outofstock" and p["id"] not in history:
            success = await format_and_send_product(p)
            if success:
                history.add(p["id"])
                save_sent_history(history)
                out_of_stock.discard(p["id"])
                save_out_of_stock(out_of_stock)
            await asyncio.sleep(1)

# ===== ربات بله (Polling) =====
async def bale_polling():
    offset = 0
    base_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/getUpdates", params={"offset": offset}, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            for upd in data.get("result", []):
                                offset = upd["update_id"] + 1
                                if "message" in upd:
                                    msg = upd["message"]
                                    chat_id = msg["chat"]["id"]
                                    user = msg.get("from", {})
                                    
                                    log_user_stats(chat_id, user.get("username"), user.get("first_name"))
                                    
                                    if msg.get("text") == "/start":
                                        keyboard = {"inline_keyboard": [[{"text": "💰 قیمت لحظه‌ای طلا", "callback_data": "get_live_gold"}]]}
                                        await send_to_bale(chat_id, "سلام! برای دریافت قیمت لحظه‌ای طلا روی دکمه زیر بزنید:", reply_markup=keyboard, title="پیام استارت")
                                elif "callback_query" in upd:
                                    cb = upd["callback_query"]
                                    chat_id = cb["message"]["chat"]["id"]
                                    user = cb.get("from", {})
                                    
                                    log_user_stats(chat_id, user.get("username"), user.get("first_name"))
                                    
                                    async with session.post(f"{base_url}/answerCallbackQuery", json={"callback_query_id": cb["id"]}) as ans: pass
                                    if cb["data"] == "get_live_gold":
                                        text = await get_gold_price_text()
                                        keyboard = {"inline_keyboard": [[{"text": "🔄 به‌روزرسانی قیمت", "callback_data": "get_live_gold"}]]}
                                        await send_to_bale(chat_id, text, reply_markup=keyboard, title="قیمت طلا (دکمه)")
        except asyncio.TimeoutError: pass
        except Exception as e: pass
        await asyncio.sleep(2)

# ===== ربات تلگرام (Polling) =====
async def telegram_polling():
    offset = 0
    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/getUpdates", params={"offset": offset, "timeout": 15}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            for upd in data.get("result", []):
                                offset = upd["update_id"] + 1
                                if "message" in upd:
                                    msg = upd["message"]
                                    chat_id = msg["chat"]["id"]
                                    user = msg.get("from", {})
                                    
                                    log_user_stats(chat_id, user.get("username"), user.get("first_name"))
                                    
                                    if msg.get("text", "").startswith("/start"):
                                        keyboard = {"inline_keyboard": [[{"text": "💰 قیمت لحظه‌ای طلا", "callback_data": "get_live_gold_telegram"}]]}
                                        await send_to_telegram(chat_id, "سلام! برای دریافت قیمت لحظه‌ای طلا روی دکمه زیر بزنید:", title="پیام استارت")
                                        data_msg = {"chat_id": chat_id, "text": "لطفا یکی از گزینه‌های زیر را انتخاب کنید:", "reply_markup": keyboard}
                                        async with session.post(f"{base_url}/sendMessage", json=data_msg) as r: pass
                                        
                                elif "callback_query" in upd:
                                    cb = upd["callback_query"]
                                    chat_id = cb["message"]["chat"]["id"]
                                    user = cb.get("from", {})
                                    
                                    log_user_stats(chat_id, user.get("username"), user.get("first_name"))
                                    
                                    async with session.post(f"{base_url}/answerCallbackQuery", json={"callback_query_id": cb["id"]}) as ans: pass
                                    
                                    if cb["data"] == "get_live_gold_telegram":
                                        text = await get_gold_price_text()
                                        keyboard = {"inline_keyboard": [[{"text": "🔄 به‌روزرسانی قیمت", "callback_data": "get_live_gold_telegram"}]]}
                                        data_msg = {"chat_id": chat_id, "text": text, "reply_markup": keyboard, "parse_mode": "Markdown"}
                                        async with session.post(f"{base_url}/sendMessage", json=data_msg) as r: pass
                                        print("✅ قیمت طلا (دکمه) به تلگرام ارسال شد.")
        except asyncio.TimeoutError: pass
        except Exception as e: pass
        await asyncio.sleep(2)

# ===== اجرا =====
async def main():
    if os.environ.get("PORT"):
        threading.Thread(target=run_web_server, daemon=True).start()

    tehran_tz = pytz.timezone('Asia/Tehran')
    scheduler = AsyncIOScheduler(timezone=tehran_tz)
    
    # قیمت طلا: هر 1 ساعت دقیقه 0 (از 9 صبح تا 11 شب + دقیقاً 00:00 بامداد)
    scheduler.add_job(send_gold_price, 'cron', hour='0,9-23/1', minute=0)
    
    # محصولات: دقیقه 0 و 30 (از 9 صبح تا 11:30 شب + دقیقاً 00:00 بامداد)
    scheduler.add_job(check_and_send_products, 'cron', hour='0,9-23', minute='0,30')
    
    # بررسی هفتگی ناموجودها
    scheduler.add_job(check_out_of_stock, 'interval', hours=168) 
    
    scheduler.start()

    asyncio.create_task(bale_polling())
    if TELEGRAM_TOKEN:
        asyncio.create_task(telegram_polling())

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ خطای اصلی: {e}")
        traceback.print_exc()
