import os
os.environ["PYTHONUNBUFFERED"] = "1"

import asyncio
import aiohttp
import json
import threading
import traceback
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask, request
from supabase import create_client, Client

# ===== خواندن تنظیمات از متغیرهای محیطی =====
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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# ===== وب‌سرور (Flask) =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Behzadgold Bot is running."

@app.route("/webhook", methods=['POST'])
def webhook():
    print("🟢 [WEBHOOK] درخواست جدید از سمت بله دریافت شد!")
    update = request.get_json()
    if update:
        print(f"📩 [WEBHOOK] محتوای آپدیت: {json.dumps(update, ensure_ascii=False)}")
        try:
            asyncio.run(process_update(update))
            print("✅ [WEBHOOK] پردازش آپدیت با موفقیت تمام شد.")
        except Exception as e:
            print(f"❌ [WEBHOOK] خطا در پردازش آپدیت: {e}")
            traceback.print_exc()
    else:
        print("⚠️ [WEBHOOK] آپدیت خالی بود.")
    return "OK", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 [FLASK] وب‌سرور در حال اجرا روی پورت {port} است...")
    app.run(host="0.0.0.0", port=port)

# ===== توابع کمکی ذخیره‌سازی (Supabase) =====
def get_last_id():
    if not supabase: 
        print("⚠️ [DB] کلاینت Supabase وجود ندارد.")
        return 0
    try:
        print("🔍 [DB] در حال خواندن last_id از دیتابیس...")
        response = supabase.table("last_orders").select("last_order_id").eq("site_name", "behzadgold_bot_last_id").execute()
        if response.data:
            val = int(response.data[0]["last_order_id"])
            print(f"✅ [DB] last_id خوانده شد: {val}")
            return val
        print("ℹ️ [DB] رکوردی برای last_id پیدا نشد. مقدار پیش‌فرض 0.")
        return 0
    except Exception as e:
        print(f"❌ [DB] خطا در خواندن last_id: {e}")
        return 0

def save_last_id(p_id):
    if not supabase: return
    try:
        print(f"💾 [DB] در حال ذخیره last_id: {p_id}")
        supabase.table("last_orders").update({"last_order_id": int(p_id)}).eq("site_name", "behzadgold_bot_last_id").execute()
        print("✅ [DB] last_id ذخیره شد.")
    except Exception as e:
        print(f"❌ [DB] خطا در ذخیره last_id: {e}")

def get_sent_history():
    if not supabase: return set()
    try:
        print("🔍 [DB] در حال خواندن تاریخچه ارسال (sent_history)...")
        response = supabase.table("last_orders").select("last_order_id").eq("site_name", "behzadgold_bot_sent_history").execute()
        if response.data and response.data[0]["last_order_id"] != 0:
            data = set(json.loads(str(response.data[0]["last_order_id"])))
            print(f"✅ [DB] تاریخچه خوانده شد. تعداد: {len(data)}")
            return data
        print("ℹ️ [DB] تاریخچه خالی است.")
        return set()
    except Exception as e:
        print(f"❌ [DB] خطا در خواندن تاریخچه: {e}")
        return set()

def save_sent_history(history_set):
    if not supabase: return
    try:
        print(f"💾 [DB] در حال ذخیره تاریخچه. تعداد: {len(history_set)}")
        supabase.table("last_orders").update({"last_order_id": json.dumps(list(history_set))}).eq("site_name", "behzadgold_bot_sent_history").execute()
        print("✅ [DB] تاریخچه ذخیره شد.")
    except Exception as e:
        print(f"❌ [DB] خطا در ذخیره تاریخچه: {e}")

def get_out_of_stock():
    if not supabase: return set()
    try:
        print("🔍 [DB] در حال خواندن لیست ناموجودها...")
        response = supabase.table("last_orders").select("last_order_id").eq("site_name", "behzadgold_bot_out_of_stock").execute()
        if response.data and response.data[0]["last_order_id"] != 0:
            data = set(json.loads(str(response.data[0]["last_order_id"])))
            print(f"✅ [DB] لیست ناموجودها خوانده شد. تعداد: {len(data)}")
            return data
        print("ℹ️ [DB] لیست ناموجودها خالی است.")
        return set()
    except Exception as e:
        print(f"❌ [DB] خطا در خواندن لیست ناموجودها: {e}")
        return set()

def save_out_of_stock(out_set):
    if not supabase: return
    try:
        print(f"💾 [DB] در حال ذخیره لیست ناموجودها. تعداد: {len(out_set)}")
        supabase.table("last_orders").update({"last_order_id": json.dumps(list(out_set))}).eq("site_name", "behzadgold_bot_out_of_stock").execute()
        print("✅ [DB] لیست ناموجودها ذخیره شد.")
    except Exception as e:
        print(f"❌ [DB] خطا در ذخیره لیست ناموجودها: {e}")

# ===== ارسال پیام (با تلاش مجدد) =====
async def send_to_bale(chat_id, text, photo_url=None, reply_markup=None):
    print(f"✉️ [BALE] در حال آماده‌سازی برای ارسال پیام به {chat_id}...")
    base_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
    data = {"chat_id": chat_id}
    if photo_url:
        data["photo"] = photo_url
        data["caption"] = text
        url = f"{base_url}/sendPhoto"
        print("🖼️ [BALE] نوع پیام: عکس")
    else:
        data["text"] = text
        url = f"{base_url}/sendMessage"
        print("📝 [BALE] نوع پیام: متن")
    if reply_markup: 
        data["reply_markup"] = reply_markup

    for attempt in range(3):
        try:
            print(f"🚀 [BALE] تلاش {attempt+1} از 3 برای ارسال...")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=20) as resp:
                    if resp.status == 200:
                        print(f"✅ [BALE] پیام با موفقیت ارسال شد.")
                        return True
                    else:
                        err_text = await resp.text()
                        print(f"⚠️ [BALE] خطای بله ({resp.status}): {err_text}")
        except Exception as e:
            print(f"⚠️ [BALE] خطای شبکه ({e}) - تلاش {attempt+1} از 3")
        await asyncio.sleep(2)
    
    print("❌ [BALE] ارسال پیام پس از 3 تلاش ناموفق بود.")
    return False

# ===== تابع ساخت متن قیمت =====
async def get_gold_price_text():
    print("📊 [PRICE] در حال دریافت قیمت طلا...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PRICE_JSON_URL, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print("✅ [PRICE] قیمت طلا با موفقیت دریافت شد.")
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
                else:
                    print(f"⚠️ [PRICE] خطای دریافت قیمت: {resp.status}")
    except Exception as e:
        print(f"❌ [PRICE] خطا در دریافت قیمت طلا: {e}")
    return "❌ خطا در دریافت قیمت طلا."

# ===== ۱. زمان‌بند قیمت طلا (برای کانال - بدون دکمه) =====
async def send_gold_price():
    print("⏰ [JOB] زمان‌بند ارسال قیمت طلا اجرا شد.")
    text = await get_gold_price_text()
    success = await send_to_bale(BALE_CHANNEL, text)
    if success:
        print("✅ [JOB] قیمت طلا به کانال ارسال شد.")
    else:
        print("❌ [JOB] ارسال قیمت طلا به کانال ناموفق بود.")

# ===== ۲. منطق صف محصولات =====
async def fetch_products(params):
    url = f"{WC_URL}/wp-json/wc/v3/products"
    final_params = {"consumer_key": WC_KEY, "consumer_secret": WC_SECRET}
    final_params.update(params)
    print(f"🌐 [API] در حال دریافت محصولات با پارامترها: {params}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=final_params, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ [API] تعداد {len(data)} محصول دریافت شد.")
                    return data
                else:
                    print(f"⚠️ [API] خطای دریافت محصولات: {resp.status}")
    except Exception as e:
        print(f"❌ [API] خطا در دریافت محصولات: {e}")
    return []

async def fetch_variations(product_id):
    url = f"{WC_URL}/wp-json/wc/v3/products/{product_id}/variations"
    params = {"per_page": 100, "consumer_key": WC_KEY, "consumer_secret": WC_SECRET}
    print(f"🌐 [API] در حال دریافت واریشن‌های محصول {product_id}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ [API] تعداد {len(data)} واریشن دریافت شد.")
                    return data
                else:
                    print(f"⚠️ [API] خطای دریافت واریشن‌ها: {resp.status}")
    except Exception as e:
        print(f"❌ [API] خطا در دریافت واریشن‌ها: {e}")
    return []

async def format_and_send_product(p):
    print(f"🛠️ [PRODUCT] در حال آماده‌سازی محصول #{p['id']}...")
    name = p.get("name", "بدون نام")
    price = p.get("price", "0")
    permalink = p.get("permalink", "")
    p_type = p.get("type", "simple")
    
    all_features = []
    weight_str = ""
    
    if p_type == "variable":
        print(f"ℹ️ [PRODUCT] محصول #{p['id']} متغیر است. دریافت واریشن‌ها...")
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
        print(f"ℹ️ [PRODUCT] محصول #{p['id']} ساده است.")
        for attr in p.get("attributes", []):
            attr_name = attr.get("name", "")
            options = attr.get("options", [])
            if options and attr_name not in ("وزن",):
                all_features.append(f"🔹 {attr_name}: {options[0]}")
            elif options and attr_name == "وزن":
                weight_str = f"⚖️ وزن: {options[0]}"

    print("📊 [PRODUCT] دریافت قیمت طلا برای محاسبه...")
    gold_price = "—"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PRICE_JSON_URL, headers=HEADERS, timeout=10) as resp:
                if resp.status == 200:
                    g_data = await resp.json()
                    gold_price = g_data.get("Geram18", "—")
    except:
        pass

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

    print(f"✉️ [PRODUCT] در حال ارسال محصول #{p['id']} به کانال...")
    success = await send_to_bale(BALE_CHANNEL, text, photo_url=photo_url)
    if success:
        print(f"✅ [PRODUCT] محصول #{p['id']} ({name}) با موفقیت ارسال شد.")
        return True
    else:
        print(f"❌ [PRODUCT] محصول #{p['id']} ({name}) ارسال نشد.")
        return False

async def check_and_send_products():
    print("\n🔍 [JOB] زمان‌بند بررسی محصولات اجرا شد.")
    last_id = get_last_id()
    history = get_sent_history()
    out_of_stock = get_out_of_stock()

    print("🌐 [JOB] دریافت 10 محصول آخر از سایت...")
    new_products = await fetch_products({"per_page": 10, "orderby": "id", "order": "desc"})
    truly_new = [p for p in new_products if p["id"] > last_id and p.get("stock_status") != "outofstock"]
    
    if truly_new:
        print(f"🎉 [JOB] {len(truly_new)} محصول جدید پیدا شد!")
        truly_new.sort(key=lambda x: x["id"]) 
        
        for p in truly_new[:BATCH_SIZE]:
            success = await format_and_send_product(p)
            if success:
                history.add(p["id"])
                save_last_id(p["id"])
                save_sent_history(history)
            else:
                print("⚠️ [JOB] ارسال ناموفق بود. تلاش بعدی...")
                return
        return

    print("⚠️ [JOB] محصول جدیدی نیست. در حال جستجو در آرشیو...")
    
    unsent = []
    page = 1
    while True:
        print(f"🌐 [JOB] دریافت صفحه {page} از آرشیو...")
        batch = await fetch_products({"per_page": 100, "page": page, "orderby": "id", "order": "desc"})
        if not batch:
            print("ℹ️ [JOB] به انتهای آرشیو رسیدیم.")
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
        print("✅ [JOB] همه محصولات (موجود) ارسال شده‌اند. صبر برای محصول جدید...")
        return

    p = unsent[0]
    print(f"ℹ️ [JOB] قدیمی‌ترین محصول ارسال نشده پیدا شد: #{p['id']}")
    success = await format_and_send_product(p)
    if success:
        history.add(p["id"])
        save_sent_history(history)
    else:
        print("⚠️ [JOB] ارسال ناموفق بود. تلاش بعدی...")

# ===== ۳. زمان‌بند هفتگی چک کردن محصولات ناموجود =====
async def check_out_of_stock():
    print("\n📦 [JOB] زمان‌بند بررسی محصولات ناموجود اجرا شد.")
    out_of_stock = get_out_of_stock()
    history = get_sent_history()
    
    if not out_of_stock:
        print("ℹ️ [JOB] لیست ناموجودها خالی است.")
        return

    print(f"ℹ️ [JOB] در حال بررسی {len(out_of_stock)} محصول ناموجود...")
    oos_list = list(out_of_stock)
    for p_id in oos_list:
        print(f"🔍 [JOB] بررسی وضعیت محصول #{p_id}...")
        p_data = await fetch_products({"include": p_id})
        if not p_data: 
            print(f"⚠️ [JOB] محصول #{p_id} در سایت پیدا نشد.")
            continue
        p = p_data[0]
        
        if p.get("stock_status") != "outofstock" and p["id"] not in history:
            print(f"🎉 [JOB] محصول #{p['id']} موجود شد! ارسال...")
            success = await format_and_send_product(p)
            if success:
                history.add(p["id"])
                save_sent_history(history)
                out_of_stock.discard(p["id"])
                save_out_of_stock(out_of_stock)
            await asyncio.sleep(1)
        else:
            print(f"ℹ️ [JOB] محصول #{p_id} هنوز ناموجود است.")

# ===== ۴. پردازش پیام‌های دریافتی از بله (Webhook) =====
async def process_update(update):
    print("⚙️ [PROCESS] شروع پردازش آپدیت...")
    base_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
    try:
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            print(f"💬 [PROCESS] پیام متنی از {chat_id} دریافت شد: {msg.get('text')}")
            if msg.get("text") == "/start":
                print("ℹ️ [PROCESS] دستور /start شناسایی شد. ارسال پاسخ...")
                keyboard = {"inline_keyboard": [[{"text": "💰 قیمت لحظه‌ای طلا", "callback_data": "get_live_gold"}]]}
                await send_to_bale(chat_id, "سلام! برای دریافت قیمت لحظه‌ای طلا روی دکمه زیر بزنید:", reply_markup=keyboard)
                print("✅ [PROCESS] پاسخ /start ارسال شد.")
        
        elif "callback_query" in update:
            cb = update["callback_query"]
            cb_id = cb["id"]
            chat_id = cb["message"]["chat"]["id"]
            cb_data = cb["data"]
            print(f"🔘 [PROCESS] دکمه فشرده شد. داده: {cb_data} از {chat_id}")
            
            async with aiohttp.ClientSession() as session:
                await session.post(f"{base_url}/answerCallbackQuery", json={"callback_query_id": cb_id})
                print("✅ [PROCESS] به CallbackQuery پاسخ داده شد.")
            
            if cb_data == "get_live_gold":
                print("ℹ️ [PROCESS] درخواست قیمت طلا از طریق دکمه.")
                text = await get_gold_price_text()
                keyboard = {"inline_keyboard": [[{"text": "🔄 به‌روزرسانی قیمت", "callback_data": "get_live_gold"}]]}
                await send_to_bale(chat_id, text, reply_markup=keyboard)
                print("✅ [PROCESS] قیمت طلا از طریق دکمه ارسال شد.")
        else:
            print("⚠️ [PROCESS] آپدیت از نوع ناشناخته بود.")
    except Exception as e:
        print(f"❌ [PROCESS] خطا در پردازش آپدیت: {e}")
        traceback.print_exc()

# ===== اجرا =====
async def main():
    print("🚀 [MAIN] برنامه در حال شروع است...")
    
    # بررسی اتصال اولیه به Supabase
    if supabase:
        print("✅ [MAIN] کلاینت Supabase ساخته شد.")
    else:
        print("❌ [MAIN] هشدار: کلاینت Supabase ساخته نشد. متغیرهای محیطی را بررسی کنید.")

    # اجرای وب‌سرور Flask در یک ترد جداگانه
    if os.environ.get("PORT"):
        print("🌐 [MAIN] در حال شروع وب‌سرور Flask...")
        web_thread = threading.Thread(target=run_web_server, daemon=True)
        web_thread.start()

    scheduler = AsyncIOScheduler()
    print("⏰ [MAIN] در حال تنظیم زمان‌بندها...")
    
    scheduler.add_job(send_gold_price, 'interval', minutes=1) 
    scheduler.add_job(check_and_send_products, 'interval', minutes=1)
    scheduler.add_job(check_out_of_stock, 'interval', hours=168) 
    
    scheduler.start()
    print("✅ [MAIN] زمان‌بندها فعال شدند. در انتظار رویدادها...")

    # حلقه بی‌نهایت برای زنده نگه داشتن برنامه
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ [MAIN] خطای اصلی: {e}")
        traceback.print_exc()
