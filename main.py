import asyncio
import logging
import os
import time
from datetime import datetime
import requests
import pandas as pd
import yfinance as yf
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = "8916738723:AAG8YR35bIX-90HGUdjllwjGkiqbongI9lk"
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "C8c6abe66da242369986f71fd1cac414").strip()

API_COUNTER = {
    "used_today": 27,
    "max_daily": 800,
    "last_reset_day": datetime.now().day
}

def increment_api_counter():
    today = datetime.now().day
    if today != API_COUNTER["last_reset_day"]:
        API_COUNTER["used_today"] = 0
        API_COUNTER["last_reset_day"] = today
    API_COUNTER["used_today"] += 1

def test_twelve_data_connection():
    """دالة لاختبار سحب البيانات عبر دمج المفتاح مباشرة في الرابط"""
    increment_api_counter()
    # دمج المفتاح مباشرة في الرابط لتجنب أي مشاكل في تمرير الـ params
    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=5min&outputsize=1&apikey={TWELVE_DATA_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if "values" in data:
            return True, data["values"][0]["close"]
        else:
            # إعادة العداد إذا فشل الطلب فعلياً ولم يتم احتسابه
            return False, data.get("message", "Unknown error")
    except Exception as e:
        return False, str(e)

def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("▶️ تشغيل التحليل (M5)", callback_data="start_trading"),
            InlineKeyboardButton("⏹️ إيقاف التداول", callback_data="stop_trading")
        ],
        [
            InlineKeyboardButton("⚡ اختبار سحب API يدوي الآن", callback_data="test_api_now")
        ],
        [
            InlineKeyboardButton("📊 حالة الحساب وعداد API", callback_data="check_status"),
            InlineKeyboardButton("🔄 إعادة ضبط الرصيد", callback_data="reset_balance")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    if "balance" not in data:
        data["balance"] = 1000.0
        data["base_stake"] = 1.0
        data["current_stake"] = 1.0
        data["is_running"] = False

    await update.message.reply_text(
        "👋 **أهلاً بك في بوت إشارات الذهب (M5):**\nاضغط على زر **⚡ اختبار سحب API يدوي الآن** للتأكد من عمل المفتاح فوراً.",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data
    chat_id = query.message.chat_id

    if "balance" not in data:
        data["balance"] = 1000.0
        data["base_stake"] = 1.0
        data["current_stake"] = 1.0
        data["is_running"] = False

    if query.data == "test_api_now":
        success, result = test_twelve_data_connection()
        if success:
            await query.edit_message_text(
                f"✅ **نجح الاتصال وسحب البيانات بنجاح!**\n• سعر الذهب الحالي: `{result}`\n• تم التحقق من المفتاح وتحديث العداد.",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"❌ **خطأ من المنصة:**\n`{result}`",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )

    elif query.data == "start_trading":
        data["is_running"] = True
        await query.edit_message_text("🟢 تم تشغيل البوت.", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

    elif query.data == "stop_trading":
        data["is_running"] = False
        await query.edit_message_text("🛑 تم إيقاف البوت.", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

    elif query.data == "check_status":
        used = API_COUNTER["used_today"]
        await query.edit_message_text(
            f"📊 **عداد الطلبات اليومي:**\n• المستهلك: `{used} / 800`",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )

    elif query.data == "reset_balance":
        data["balance"] = 1000.0
        await query.edit_message_text("🔄 تم إعادة ضبط الرصيد.", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

    elif query.data == "main_menu":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

def main():
    keep_alive()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling()

if __name__ == '__main__':
    main()
