
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
