
import os
import asyncio
import aiohttp
import json
import threading
import traceback
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from supabase import create_client, Client


# =====================================================
# تنظیمات محیطی
# =====================================================

WC_URL = os.environ.get("WC_URL")
WC_KEY = os.environ.get("WC_KEY")
WC_SECRET = os.environ.get("WC_SECRET")

BALE_TOKEN = os.environ.get("BALE_TOKEN")
BALE_CHANNEL = os.environ.get("BALE_CHANNEL")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

PRICE_JSON_URL = os.environ.get("PRICE_JSON_URL")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


# =====================================================
# اتصال به Supabase
# =====================================================

supabase: Client = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if SUPABASE_URL and SUPABASE_KEY
    else None
)


# =====================================================
# وب سرور
# =====================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Behzadgold Bot is running."


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =====================================================
# ذخیره سازی اطلاعات
# =====================================================

def get_sent_history():

    if not supabase:
        return set()

    try:
        response = (
            supabase.table("last_orders")
            .select("sent_history")
            .eq("site_name", "behzadgold_bot_sent_history")
            .execute()
        )

        if response.data and response.data[0].get("sent_history"):
            return set(
                json.loads(str(response.data[0]["sent_history"]))
            )

        return set()

    except Exception as e:
        print(f"خطا در دریافت تاریخچه: {e}")
        return set()


def save_sent_history(history_set):

    if not supabase:
        return

    try:
        history_str = json.dumps(list(history_set))

        supabase.table("last_orders").update({
            "sent_history": history_str
        }).eq(
            "site_name", "behzadgold_bot_sent_history"
        ).execute()

    except Exception as e:
        print(f"خطا در ذخیره تاریخچه: {e}")


def get_out_of_stock():

    if not supabase:
        return set()

    try:
        response = (
            supabase.table("last_orders")
            .select("sent_history")
            .eq("site_name", "behzadgold_bot_out_of_stock")
            .execute()
        )

        if response.data and response.data[0].get("sent_history"):
            return set(
                json.loads(str(response.data[0]["sent_history"]))
            )

        return set()

    except Exception as e:
        print(f"خطا در دریافت محصولات ناموجود: {e}")
        return set()


def save_out_of_stock(out_set):

    if not supabase:
        return

    try:
        history_str = json.dumps(list(out_set))

        supabase.table("last_orders").update({
            "sent_history": history_str
        }).eq(
            "site_name", "behzadgold_bot_out_of_stock"
        ).execute()

    except Exception as e:
        print(f"خطا در ذخیره محصولات ناموجود: {e}")


# =====================================================
# ارسال پیام به بله
# =====================================================

async def send_to_bale(
    chat_id,
    text,
    photo_url=None,
    reply_markup=None,
    title=""
):

    if not BALE_TOKEN or not chat_id:
        print("⚠️ توکن یا شناسه بله تنظیم نشده است.")
        return False

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

                async with session.post(
                    url,
                    json=data,
                    timeout=20
                ) as resp:

                    if resp.status == 200:
                        print(f"✅ {title} به بله ارسال شد.")
                        return True

                    print(
                        f"❌ خطای ارسال به بله: "
                        f"{resp.status} - {await resp.text()}"
                    )

        except Exception as e:
            print(f"❌ خطای شبکه بله: {e}")

        await asyncio.sleep(5)


# =====================================================
# ارسال پیام به تلگرام
# =====================================================

async def send_to_telegram(
    chat_id,
    text,
    photo_url=None,
    reply_markup=None,
    title=""
):

    if not TELEGRAM_TOKEN or not chat_id:
        print("⚠️ توکن یا Chat ID تلگرام تنظیم نشده است.")
        return False

    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    if photo_url:

        url = f"{base_url}/sendPhoto"

        data = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": text,
            "parse_mode": "Markdown"
        }

    else:

        url = f"{base_url}/sendMessage"

        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

    if reply_markup:
        data["reply_markup"] = reply_markup

    while True:

        try:

            async with aiohttp.ClientSession() as session:

                async with session.post(
                    url,
                    json=data,
                    timeout=20
                ) as resp:

                    if resp.status == 200:
                        print(f"✅ {title} به تلگرام ارسال شد.")
                        return True

                    err = await resp.text()

                    if (
                        "can't parse entities" in err
                        and "parse_mode" in data
                    ):

                        del data["parse_mode"]

                        print(
                            "⚠️ خطای فرمت بندی تلگرام. "
                            "تلاش بدون فرمت..."
                        )

                        continue

                    print(f"❌ خطای تلگرام: {err}")

        except Exception as e:
            print(f"❌ خطای شبکه تلگرام: {e}")

        await asyncio.sleep(5)


# =====================================================
# دریافت قیمت طلا
# =====================================================

async def get_gold_price_text():

    try:

        async with aiohttp.ClientSession() as session:

            async with session.get(
                PRICE_JSON_URL,
                headers=HEADERS,
                timeout=15
            ) as resp:

                if resp.status == 200:

                    data = await resp.json()

                    return (
                        f"📊 *قیمت لحظه‌ای طلا و سکه*\n\n"

                        f"🥇 هر گرم طلای ۱۸ عیار: "
                        f"{data.get('Geram18', '—')} تومان\n"

                        f"🔄 هر گرم طلای تعویضی: "
                        f"{data.get('Taviz', '—')} تومان\n"

                        f"💧 هر گرم طلای آب شده: "
                        f"{data.get('ForushAbshode', '—')} تومان\n\n"

                        f"🪙 سکه یک گرمی: "
                        f"{data.get('YekGerami', '—')} تومان\n"

                        f"🪙 سکه امامی جدید: "
                        f"{data.get('Tamam', '—')} تومان\n"

                        f"🪙 سکه تمام تاریخ پایین: "
                        f"{data.get('SekeGhadim', '—')} تومان\n"

                        f"🪙 سکه تمام طرح قدیم: "
                        f"{data.get('SekeGhadim', '—')} تومان\n"

                        f"🪙 سکه نیم تاریخ پایین: "
                        f"{data.get('NimZir86', '—')} تومان\n"

                        f"🪙 سکه نیم بهار آزادی: "
                        f"{data.get('Nim', '—')} تومان\n"

                        f"🪙 سکه ربع تاریخ پایین: "
                        f"{data.get('RobZir86', '—')} تومان\n"

                        f"🪙 سکه ربع بهار آزادی: "
                        f"{data.get('Rob', '—')} تومان\n\n"

                        f"🌍 اونس جهانی طلا: "
                        f"{data.get('Ons', '—')} دلار\n\n"

                        f"📅 تاریخ: {data.get('Date', '—')} "
                        f"- {data.get('Time', '—')}"
                    )

    except Exception as e:

        print(f"❌ خطا در دریافت قیمت طلا: {e}")

    return "❌ خطا در دریافت قیمت طلا."


# =====================================================
# ارسال خودکار قیمت طلا
# =====================================================

async def send_gold_price():

    text = await get_gold_price_text()

    await send_to_bale(
        BALE_CHANNEL,
        text,
        title="قیمت طلا"
    )

    await send_to_telegram(
        TELEGRAM_CHAT_ID,
        text,
        title="قیمت طلا"
    )


# =====================================================
# ربات بله - دریافت دستورات
# =====================================================

async def bale_polling():

    if not BALE_TOKEN:
        print("⚠️ توکن بله تنظیم نشده است.")
        return

    offset = 0

    base_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

    while True:

        try:

            async with aiohttp.ClientSession() as session:

                async with session.get(
                    f"{base_url}/getUpdates",
                    params={"offset": offset},
                    timeout=15
                ) as resp:

                    if resp.status == 200:

                        data = await resp.json()

                        if data.get("ok"):

                            for upd in data.get("result", []):

                                offset = upd["update_id"] + 1

                                if "message" in upd:

                                    msg = upd["message"]

                                    chat_id = msg["chat"]["id"]

                                    if msg.get("text") == "/start":

                                        keyboard = {
                                            "inline_keyboard": [[
                                                {
                                                    "text": "💰 قیمت لحظه‌ای طلا",
                                                    "callback_data": "get_live_gold"
                                                }
                                            ]]
                                        }

                                        await send_to_bale(
                                            chat_id,
                                            "سلام! 👋\n\n"
                                            "برای دریافت قیمت لحظه‌ای طلا "
                                            "روی دکمه زیر بزنید:",
                                            reply_markup=keyboard,
                                            title="پیام استارت بله"
                                        )

                                elif "callback_query" in upd:

                                    cb = upd["callback_query"]

                                    async with session.post(
                                        f"{base_url}/answerCallbackQuery",
                                        json={
                                            "callback_query_id": cb["id"]
                                        }
                                    ):
                                        pass

                                    if cb.get("data") == "get_live_gold":

                                        text = await get_gold_price_text()

                                        keyboard = {
                                            "inline_keyboard": [[
                                                {
                                                    "text": "🔄 به‌روزرسانی قیمت",
                                                    "callback_data": "get_live_gold"
                                                }
                                            ]]
                                        }

                                        await send_to_bale(
                                            cb["message"]["chat"]["id"],
                                            text,
                                            reply_markup=keyboard,
                                            title="قیمت طلا بله"
                                        )

        except asyncio.TimeoutError:
            pass

        except Exception as e:
            print(f"❌ خطای Polling بله: {e}")

        await asyncio.sleep(2)


# =====================================================
# ربات تلگرام - دریافت دستورات
# =====================================================

async def telegram_polling():

    if not TELEGRAM_TOKEN:
        print("⚠️ توکن تلگرام تنظیم نشده است.")
        return

    offset = 0

    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    print("✅ ربات تلگرام فعال شد.")

    while True:

        try:

            async with aiohttp.ClientSession() as session:

                async with session.get(
                    f"{base_url}/getUpdates",

                    params={
                        "offset": offset,
                        "timeout": 25,
                        "allowed_updates": json.dumps([
                            "message",
                            "callback_query"
                        ])
                    },

                    timeout=35

                ) as resp:

                    if resp.status != 200:

                        print(
                            f"❌ خطای دریافت اطلاعات تلگرام: "
                            f"{resp.status}"
                        )

                        await asyncio.sleep(3)
                        continue

                    data = await resp.json()

                    if data.get("ok"):

                        for upd in data.get("result", []):

                            offset = upd["update_id"] + 1

                            # دریافت پیام کاربر

                            if "message" in upd:

                                msg = upd["message"]

                                chat_id = msg["chat"]["id"]

                                message_text = msg.get("text", "")

                                command = (
                                    message_text.split()[0].split("@")[0]
                                    if message_text
                                    else ""
                                )

                                # دستور Start

                                if command == "/start":

                                    keyboard = {
                                        "inline_keyboard": [[
                                            {
                                                "text": "💰 قیمت لحظه‌ای طلا",
                                                "callback_data": "get_live_gold"
                                            }
                                        ]]
                                    }

                                    await send_to_telegram(
                                        chat_id,

                                        "سلام! 👋\n\n"
                                        "به ربات قیمت طلا خوش آمدید.\n\n"
                                        "برای مشاهده قیمت لحظه‌ای طلا "
                                        "روی دکمه زیر بزنید:",

                                        reply_markup=keyboard,

                                        title="پیام استارت تلگرام"
                                    )

                            # دریافت کلیک روی دکمه

                            elif "callback_query" in upd:

                                cb = upd["callback_query"]

                                # پاسخ به Callback

                                async with session.post(
                                    f"{base_url}/answerCallbackQuery",

                                    json={
                                        "callback_query_id": cb["id"]
                                    },

                                    timeout=10

                                ) as ans:
                                    pass

                                if cb.get("data") == "get_live_gold":

                                    message = cb.get("message", {})

                                    chat = message.get("chat", {})

                                    chat_id = chat.get("id")

                                    if not chat_id:
                                        continue

                                    text = await get_gold_price_text()

                                    keyboard = {
                                        "inline_keyboard": [[
                                            {
                                                "text": "🔄 به‌روزرسانی قیمت",
                                                "callback_data": "get_live_gold"
                                            }
                                        ]]
                                    }

                                    await send_to_telegram(
                                        chat_id,
                                        text,
                                        reply_markup=keyboard,
                                        title="قیمت لحظه‌ای طلا تلگرام"
                                    )

        except asyncio.TimeoutError:
            pass

        except Exception as e:

            print(f"❌ خطای Polling تلگرام: {e}")

            await asyncio.sleep(3)

        await asyncio.sleep(2)


# =====================================================
# دریافت محصولات ووکامرس
# =====================================================

async def fetch_products(params):

    url = f"{WC_URL}/wp-json/wc/v3/products"

    final_params = {
        "consumer_key": WC_KEY,
        "consumer_secret": WC_SECRET
    }

    final_params.update(params)

    try:

        async with aiohttp.ClientSession() as session:

            async with session.get(
                url,
                params=final_params,
                headers=HEADERS,
                timeout=15
            ) as resp:

                if resp.status == 200:
                    return await resp.json()

                print(f"❌ خطای ووکامرس: {resp.status}")

    except Exception as e:
        print(f"❌ خطای دریافت محصولات: {e}")

    return []


# =====================================================
# دریافت متغیرهای محصولات
# =====================================================

async def fetch_variations(product_id):

    url = (
        f"{WC_URL}/wp-json/wc/v3/products/"
        f"{product_id}/variations"
    )

    params = {
        "per_page": 100,
        "consumer_key": WC_KEY,
        "consumer_secret": WC_SECRET
    }

    try:

        async with aiohttp.ClientSession() as session:

            async with session.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=15
            ) as resp:

                if resp.status == 200:
                    return await resp.json()

    except Exception as e:
        print(f"❌ خطای دریافت تنوع محصول: {e}")

    return []


# =====================================================
# قالب بندی و ارسال محصول
# =====================================================

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

                if attr.get("name") == "وزن" and attr.get("option"):

                    weights.add(attr.get("option"))

        if weights:

            weights_str = "، ".join(sorted(list(weights)))

            weight_str = f"⚖️ موجود در وزن‌های: {weights_str}"

    else:

        for attr in p.get("attributes", []):

            attr_name = attr.get("name", "")

            options = attr.get("options", [])

            if options and attr_name not in ("وزن",):

                all_features.append(
                    f"🔹 {attr_name}: {options[0]}"
                )

            elif options and attr_name == "وزن":

                weight_str = f"⚖️ وزن: {options[0]}"

    # دریافت قیمت طلا برای محاسبه محصول

    gold_price = "—"

    try:

        async with aiohttp.ClientSession() as session:

            async with session.get(
                PRICE_JSON_URL,
                headers=HEADERS,
                timeout=10
            ) as resp:

                if resp.status == 200:

                    g_data = await resp.json()

                    gold_price = g_data.get("Geram18", "—")

    except Exception as e:
        print(f"خطا در دریافت قیمت طلای محصول: {e}")

    # ساخت متن محصول

    text = f"✨ *{name}* ✨\n\n"

    if weight_str:

        text += f"{weight_str}\n\n"

    text += (
        "✅ عیار طلا: ۱۸ عیار است\n"
        "✅ فروش با فاکتور رسمی\n\n"
    )

    text += (
        f"💰 قیمت: {price} تومان\n"
        f"📈 (این قیمت با طلای {gold_price} تومان محاسبه شده است)\n\n"
    )

    if all_features:

        text += (
            "📋 مشخصات:\n"
            + "\n".join(all_features)
            + "\n\n"
        )

    text += (
        f"🏢 آدرس فروشگاه:*\n"
        f"ساوه، خیابان سوم شعبان، پاساژ سامان، پلاک ۸\n"
        f"☎️ 42226350 (086)\n\n"
        f"🔗 مشاهده محصول در سایت:\n"
        f"{permalink}"
    )

    images = p.get("images", [])

    photo_url = images[0]["src"] if images else None

    title = f"محصول {name}"

    # ارسال به بله

    await send_to_bale(
        BALE_CHANNEL,
        text,
        photo_url=photo_url,
        title=title
    )

    # ارسال به تلگرام

    await send_to_telegram(
        TELEGRAM_CHAT_ID,
        text,
        photo_url=photo_url,
        title=title
    )

    return True


# =====================================================
# بررسی محصولات جدید
# =====================================================

async def check_and_send_products():

    history = get_sent_history()

    out_of_stock = get_out_of_stock()

    all_products = []

    page = 1

    while True:

        batch = await fetch_products({
            "per_page": 100,
            "page": page,
            "orderby": "id",
            "order": "desc",
            "status": "publish"
        })

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


# =====================================================
# بررسی محصولات ناموجود
# =====================================================

async def check_out_of_stock():

    out_of_stock = get_out_of_stock()

    history = get_sent_history()

    if not out_of_stock:
        return

    for p_id in list(out_of_stock):

        p_data = await fetch_products({
            "include": p_id,
            "status": "publish"
        })

        if not p_data:
            continue

        p = p_data[0]

        if (
            p.get("stock_status") != "outofstock"
            and p["id"] not in history
        ):

            success = await format_and_send_product(p)

            if success:

                history.add(p["id"])

                save_sent_history(history)

                out_of_stock.discard(p["id"])

                save_out_of_stock(out_of_stock)


# =====================================================
# اجرای اصلی برنامه
# =====================================================

async def main():

    print("🚀 Behzadgold Bot started!")

    # اجرای وب سرور

    if os.environ.get("PORT"):

        threading.Thread(
            target=run_web_server,
            daemon=True
        ).start()

    # تنظیم ساعت تهران

    tehran_tz = pytz.timezone("Asia/Tehran")

    scheduler = AsyncIOScheduler(
        timezone=tehran_tz
    )

    # ================================================
    # زمان بندی ارسال قیمت طلا
    # هر نیم ساعت از 08:00 تا 23:30
    # ================================================

    scheduler.add_job(
        send_gold_price,
        "cron",
        hour="9-24",
        minute="0,30",
        id="gold_price_job",
        replace_existing=True,
        coalesce=True,
        max_instances=1
    )

    # ================================================
    # زمان بندی ارسال محصولات
    # هر یک ساعت از 08:00 تا 23:00
    # ================================================

    scheduler.add_job(
        check_and_send_products,
        "cron",
        hour="9-24",
        minute=0,
        id="products_job",
        replace_existing=True,
        coalesce=True,
        max_instances=1
    )

    # ================================================
    # بررسی محصولات ناموجود
    # هر 168 ساعت
    # ================================================

    scheduler.add_job(
        check_out_of_stock,
        "interval",
        hours=168,
        id="out_of_stock_job",
        replace_existing=True,
        max_instances=1
    )

    scheduler.start()

    print("✅ زمان بندی ارسال قیمت طلا فعال شد.")
    print("✅ زمان بندی محصولات فعال شد.")

    # اجرای هم زمان ربات بله و تلگرام

    await asyncio.gather(
        bale_polling(),
        telegram_polling()
    )


# =====================================================
# شروع برنامه
# =====================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print("ربات متوقف شد.")

    except Exception as e:

        print(f"❌ خطای اصلی: {e}")

        traceback.print_exc()
