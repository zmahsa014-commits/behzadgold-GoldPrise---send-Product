import os
os.environ["PYTHONUNBUFFERED"] = "1"

import asyncio
import aiohttp
import json
import threading
import traceback
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from supabase import create_client, Client

# ===== خواندن تنظیمات (از متغیرهای محیطی) =====
WC_URL = os.environ.get("WC_URL")
WC_KEY = os.environ.get("WC_KEY")
WC_SECRET = os.environ.get("WC_SECRET")

BALE_TOKEN = os.environ.get("BALE_TOKEN")
BALE_CHANNEL = os.environ.get("BALE_CHANNEL")
PRICE_JSON_URL = os.environ.get("PRICE_JSON_URL")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

BATCH_SIZE = 1 

# ===== اتصال به Supabase =====
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# اگر متغیرها تنظیم شده باشند، کلاینت ساخته می‌شود
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# ===== وب‌سرور =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Behzadgold Bot is running."

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ===== توابع کمکی ذخیره‌سازی (Supabase) =====
def get_last_id():
    if not supabase: return 0
    try:
        response = supabase.table("last_orders").select("last_order_id").eq("site_name", "behzadgold_bot_last_id").execute()
        if response.data:
            return int(response.data[0]["last_order_id"])
        return 0
    except Exception as e:
        print(f"❌ DB Read Error (last_id): {e}")
        return 0

def save_last_id(p_id):
    if not supabase: return
    try:
        supabase.table("last_orders").update({"last_order_id": int(p_id)}).eq("site_name", "behzadgold_bot_last_id").execute()
    except Exception as e:
        print(f"❌ DB Write Error (last_id): {e}")

def get_sent_history():
    if not supabase: return set()
    try:
        response = supabase.table("last_orders").select("last_order_id").eq("site_name", "behzadgold_bot_sent_history").execute()
        if response.data and response.data[0]["last_order_id"] != 0:
            return set(json.loads(str(response.data[0]["last_order_id"])))
        return set()
    except Exception as e:
        print(f"❌ DB Read Error (history): {e}")
        return set()

def save_sent_history(history_set):
    if not supabase: return
    try:
        supabase.table("last_orders").update({"last_order_id": json.dumps(list(history_set))}).eq("site_name", "behzadgold_bot_sent_history").execute()
    except Exception as e:
        print(f"❌ DB Write Error (history): {e}")

def get_out_of_stock():
    if not supabase: return set()
    try:
        response = supabase.table("last_orders").select("last_order_id").eq("site_name", "behzadgold_bot_out_of_stock").execute()
        if response.data and response.data[0]["last_order_id"] != 0:
            return set(json.loads(str(response.data[0]["last_order_id"])))
        return set()
    except Exception as e:
        print(f"❌ DB Read Error (out_of_stock): {e}")
        return set()

def save_out_of_stock(out_set):
    if not supabase: return
    try:
        supabase.table("last_orders").update({"last_order_id": json.dumps(list(out_set))}).eq("site_name", "behzadgold_bot_out_of_stock").execute()
    except Exception as e:
        print(f"❌ DB Write Error (out_of_stock): {e}")

# ===== ارسال پیام (با تلاش مجدد) =====
async def send_to_bale(chat_id, text, photo_url=None, reply_markup=None):
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

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=20) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        print(f"⚠️ خطای بله ({resp.status}) - تلاش {attempt+1} از 3")
        except Exception as e:
            print(f"⚠️ خطای شبکه ({e}) - تلاش {attempt+1} از 3")
        await asyncio.sleep(2)
    
    return False

# ===== تابع ساخت متن قیمت =====
async def get_gold_price_text():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PRICE_JSON_URL, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = (
                        f"📊 **قیمت لحظه‌ای طلا و سکه**\n\n"
                        f"🥇 هر گرم طلای ۱۸ عیار: **{data.get('Geram18', '—')}** تومان\n"
                        f"🔄 هر گرم طلای تعویضی: **{data.get('Taviz', '—')}** تومان\n"
                        f"💧 هر گرم طلای آب شده: **{data.get('ForushAbshode', '—')}** تومان\n\n"
                        f"🪙 سکه یک گرمی: **{data.get('YekGerami', '—')}** تومان\n"
                        f"🪙 سکه امامی جدید: **{data.get('Tamam', '—')}** تومان\n"
                        f"🪙 سکه تمام تاریخ پایین: **{data.get('SekeGhadim', '—')}** تومان\n"
                        f"🪙 سکه تمام طرح قدیم: **{data.get('SekeGhadim', '—')}** تومان\n"
                        f"🪙 سکه نیم تاریخ پایین: **{data.get('NimZir86', '—')}** تومان\n"
                        f"🪙 سکه نیم بهار آزادی: **{data.get('Nim', '—')}** تومان\n"
                        f"🪙 سکه ربع تاریخ پایین: **{data.get('RobZir86', '—')}** تومان\n"
                        f"🪙 سکه ربع بهار آزادی: **{data.get('Rob', '—')}** تومان\n\n"
                        f"🌍 اونس جهانی طلا: **{data.get('Ons', '—')}** دلار\n\n"
                        f"📅 تاریخ: {data.get('Date', '—')} - {data.get('Time', '—')}"
                    )
                    return text
    except Exception as e:
        print(f"❌ خطا در دریافت قیمت طلا: {e}")
    return "❌ خطا در دریافت قیمت طلا."

# ===== ۱. زمان‌بند قیمت طلا (برای کانال - بدون دکمه) =====
async def send_gold_price():
    print("⏰ در حال ارسال قیمت طلا به کانال...")
    text = await get_gold_price_text()
    await send_to_bale(BALE_CHANNEL, text)
    print("✅ قیمت طلا به کانال ارسال شد.")

# ===== ۲. منطق صف محصولات =====
async def fetch_products(params):
    url = f"{WC_URL}/wp-json/wc/v3/products"
    final_params = {"consumer_key": WC_KEY, "consumer_secret": WC_SECRET}
    final_params.update(params)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=final_params, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        print(f"❌ خطا در API: {e}")
    return []

async def fetch_variations(product_id):
    url = f"{WC_URL}/wp-json/wc/v3/products/{product_id}/variations"
    params = {"per_page": 100, "consumer_key": WC_KEY, "consumer_secret": WC_SECRET}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        print(f"❌ خطا در دریافت واریشن‌ها: {e}")
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

    # ساخت متن (ترتیب جدید)
    text = f"✨ **{name}** ✨\n\n"
    
    if weight_str:
        text += f"{weight_str}\n\n"

    text += f"💰 قیمت: {price} تومان\n"
    text += f"📈 (این قیمت با طلای {gold_price} تومان محاسبه شده است)\n\n"
    
    if all_features:
        text += "📋 **مشخصات:**\n"
        text += "\n".join(all_features) + "\n\n"

    text += "✅ عیار طلا: ۱۸ عیار است\n"
    text += "✅ فروش با فاکتور رسمی\n\n"
        
    text += (
        f"🏢 **آدرس فروشگاه:**\n"
        f"ساوه، خیابان سوم شعبان، پاساژ سامان، پلاک ۸\n"
        f"☎️ 42226350 (086)\n\n"
        f"🔗 [مشاهده محصول در سایت]({permalink})"
    )

    images = p.get("images", [])
    photo_url = images[0]["src"] if images else None

    success = await send_to_bale(BALE_CHANNEL, text, photo_url=photo_url)
    if success:
        print(f"✅ محصول #{p['id']} ({name}) ارسال شد.")
        return True
    else:
        print(f"❌ محصول #{p['id']} ({name}) ارسال نشد.")
        return False

async def check_and_send_products():
    print("🔍 در حال بررسی محصولات...")
    last_id = get_last_id()
    history = get_sent_history()
    out_of_stock = get_out_of_stock()

    new_products = await fetch_products({"per_page": 10, "orderby": "id", "order": "desc"})
    truly_new = [p for p in new_products if p["id"] > last_id and p.get("stock_status") != "outofstock"]
    
    if truly_new:
        print(f"🎉 {len(truly_new)} محصول جدید پیدا شد!")
        truly_new.sort(key=lambda x: x["id"]) 
        
        for p in truly_new[:BATCH_SIZE]:
            success = await format_and_send_product(p)
            if success:
                history.add(p["id"])
                save_last_id(p["id"])
                save_sent_history(history)
            else:
                print("⚠️ ارسال ناموفق بود. تلاش بعدی...")
                return
        return

    print("⚠️ محصول جدیدی نیست. در حال جستجو در آرشیو...")
    
    unsent = []
    page = 1
    while True:
        batch = await fetch_products({"per_page": 100, "page": page, "orderby": "id", "order": "desc"})
        if not batch:
            break
            
        for p in batch:
            if p.get("stock_status") == "outofstock":
                out_of_stock.add(p["id"])
                continue
            if p["id"] in history:
                continue
            unsent.append(p)
            break 
        
        if unsent:
            break
        page += 1
        if page > 100:
            break

    save_out_of_stock(out_of_stock)

    if not unsent:
        print("✅ همه محصولات (موجود) ارسال شده‌اند. صبر برای محصول جدید...")
        return

    p = unsent[0]
    success = await format_and_send_product(p)
    if success:
        history.add(p["id"])
        save_sent_history(history)
    else:
        print("⚠️ ارسال ناموفق بود. تلاش بعدی...")

# ===== ۳. زمان‌بند هفتگی چک کردن محصولات ناموجود =====
async def check_out_of_stock():
    print("📦 در حال بررسی هفتگی محصولات ناموجود...")
    out_of_stock = get_out_of_stock()
    history = get_sent_history()
    
    if not out_of_stock:
        return

    oos_list = list(out_of_stock)
    for p_id in oos_list:
        p_data = await fetch_products({"include": p_id})
        if not p_data: continue
        p = p_data[0]
        
        if p.get("stock_status") != "outofstock" and p["id"] not in history:
            print(f"🎉 محصول #{p['id']} موجود شد! ارسال...")
            success = await format_and_send_product(p)
            if success:
                history.add(p["id"])
                save_sent_history(history)
                out_of_stock.discard(p["id"])
                save_out_of_stock(out_of_stock)
            await asyncio.sleep(1)

# ===== ۴. ربات بله (دکمه استارت) =====
async def bale_polling():
    offset = 0
    base_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/getUpdates", params={"offset": offset}, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            for upd in data.get("result", []):
                                offset = upd["update_id"] + 1
                                
                                if "message" in upd:
                                    msg = upd["message"]
                                    chat_id = msg["chat"]["id"]
                                    if msg.get("text") == "/start":
                                        keyboard = {"inline_keyboard": [[{"text": "💰 قیمت لحظه‌ای طلا", "callback_data": "get_live_gold"}]]}
                                        await send_to_bale(chat_id, "سلام! برای دریافت قیمت لحظه‌ای طلا روی دکمه زیر بزنید:", reply_markup=keyboard)
                                
                                elif "callback_query" in upd:
                                    cb = upd["callback_query"]
                                    cb_id = cb["id"]
                                    chat_id = cb["message"]["chat"]["id"]
                                    cb_data = cb["data"]
                                    
                                    async with session.post(f"{base_url}/answerCallbackQuery", json={"callback_query_id": cb_id}) as ans: pass
                                    
                                    if cb_data == "get_live_gold":
                                        text = await get_gold_price_text()
                                        keyboard = {"inline_keyboard": [[{"text": "🔄 به‌روزرسانی قیمت", "callback_data": "get_live_gold"}]]}
                                        await send_to_bale(chat_id, text, reply_markup=keyboard)
        except asyncio.TimeoutError: pass
        except Exception as e: print(f"❌ خطای شبکه در polling: {e}")
        
        await asyncio.sleep(2)

# ===== اجرا =====
async def main():
    if os.environ.get("PORT"):
        web_thread = threading.Thread(target=run_web_server, daemon=True)
        web_thread.start()

    scheduler = AsyncIOScheduler()
    
    scheduler.add_job(send_gold_price, 'interval', minutes=1) 
    scheduler.add_job(check_and_send_products, 'interval', minutes=1)
    scheduler.add_job(check_out_of_stock, 'interval', hours=168) 
    
    scheduler.start()
    print("⏰ زمان‌بندها فعال شدند.")

    asyncio.create_task(bale_polling())
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ خطای اصلی: {e}")
        traceback.print_exc()
