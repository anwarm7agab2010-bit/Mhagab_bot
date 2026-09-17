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
    """دالة لاختبار سحب البيانات مباشرة وزيادة العداد"""
    increment_api_counter()
    params = {
        "symbol": "XAU/USD",
        "interval": "5min",
        "outputsize": 1,
        "apikey": TWELVE_DATA_API_KEY
    }
    try:
        response = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=10)
        data = response.json()
        if "values" in data:
            return True, data["values"][0]["close"]
        else:
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

def stake_selection_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("1$", callback_data="set_stake_1"),
            InlineKeyboardButton("2$", callback_data="set_stake_2"),
            InlineKeyboardButton("5$", callback_data="set_stake_5")
        ],
        [
            InlineKeyboardButton("🔙 العودة", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_market_signals():
    try:
        increment_api_counter()
        params = {
            "symbol": "XAU/USD",
            "interval": "5min",
            "outputsize": 100,
            "apikey": TWELVE_DATA_API_KEY
        }
        response = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=10)
        data = response.json()

        if "values" not in data or len(data["values"]) < 50:
            return "WAIT", 0, 0, 0, 0, 0, 0, 0, ""

        df = pd.DataFrame(data["values"]).iloc[::-1].reset_index(drop=True)
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        current_price = close.iloc[-1]

        ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1] if len(close) >= 200 else close.ewm(span=len(close), adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        upper_band = (sma20 + (2 * std20)).iloc[-1]
        lower_band = (sma20 - (2 * std20)).iloc[-1]

        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        current_rsi = (100 - (100 / (1 + rs))).iloc[-1]

        low_5 = low.rolling(window=5).min()
        high_5 = high.rolling(window=5).max()
        stoch_k = (100 * ((close - low_5) / (high_5 - low_5))).rolling(window=3).mean().iloc[-1]

        score = 60
        signal = "CALL" if current_price > ema200 else "PUT"
        strength_text = "⭐⭐⭐ 60% (اختباري)"

        return signal, current_price, upper_band, lower_band, current_rsi, stoch_k, ema200, score, strength_text
    except Exception:
        return "WAIT", 0, 0, 0, 0, 0, 0, 0, ""

async def trading_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    while data.get("is_running", False):
        signal, price, upper, lower, rsi, stoch, ema200, score, strength_text = get_market_signals()
        stake = data.get("current_stake", 1.0)
        
        if price > 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔥 **إشارة الذهب (M5):**\n• السعر الحالي: `{price:.2f}`\n• الاتجاه: `{signal}`\n• RSI: `{rsi:.1f}`",
                parse_mode="Markdown"
            )
            await asyncio.sleep(300)
        else:
            await asyncio.sleep(30)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    if "balance" not in data:
        data["balance"] = 1000.0
        data["base_stake"] = 1.0
        data["current_stake"] = 1.0
        data["is_running"] = False

    await update.message.reply_text(
        "👋 **أهلاً بك في بوت إشارات الذهب (M5):**\nاضغط على زر **⚡ اختبار سحب API يدوي الآن** لتجبار العداد على التحرك فوراً.",
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
                f"✅ **نجح الاتصال وسحب البيانات!**\n• السعر الحالي للذهب: `{result}`\n• تم استهلاك طلب API جديد.\n• اذهب لموقع Twelve Data وعمل Refresh لتجد العداد تحرك من 27 إلى 28!",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"❌ **فشل الطلب:**\n`{result}`",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )

    elif query.data == "start_trading":
        data["is_running"] = True
        await query.edit_message_text("🟢 تم تشغيل البوت.", reply_markup=main_menu_keyboard(), parse_mode="Markdown")
        asyncio.create_task(trading_loop(chat_id, context))

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
