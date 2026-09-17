import asyncio
import logging
import os
import time
from datetime import datetime
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

def test_yfinance_connection():
    """اختبار سحب بيانات الذهب عبر yfinance بدون مفتاح API"""
    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="1d", interval="5m")
        if not df.empty:
            current_price = df['Close'].iloc[-1]
            return True, current_price
        else:
            return False, "البيانات فارغة أو السوق مغلق"
    except Exception as e:
        return False, str(e)

def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("▶️ تشغيل التحليل (M5)", callback_data="start_trading"),
            InlineKeyboardButton("⏹️ إيقاف التداول", callback_data="stop_trading")
        ],
        [
            InlineKeyboardButton("⚡ اختبار سحب السعر الآن (yfinance)", callback_data="test_api_now")
        ],
        [
            InlineKeyboardButton("📊 حالة البوت", callback_data="check_status"),
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
        "👋 **أهلاً بك في بوت إشارات الذهب (M5 - بدون مفتاح API):**\n"
        "يعتمد هذا الإصدار على بيانات `yfinance` المباشرة للذهب (`GC=F`).\n"
        "اضغط على زر **⚡ اختبار سحب السعر الآن** للتأكد من عمل السحب فوراً.",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data

    if "balance" not in data:
        data["balance"] = 1000.0
        data["base_stake"] = 1.0
        data["current_stake"] = 1.0
        data["is_running"] = False

    if query.data == "test_api_now":
        success, result = test_yfinance_connection()
        if success:
            await query.edit_message_text(
                f"✅ **نجح سحب السعر بنجاح تام!**\n• سعر عقود الذهب (GC=F): `{result:.2f}`\n• لا توجد حاجة لأي مفتاح API خارجي بعد الآن.",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"❌ **تنبيه:**\n`{result}`\n*(ملاحظة: إذا كان السوق مغلقاً في عطلة نهاية الأسبوع، قد لا توجد بيانات جديدة لحظية)*",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )

    elif query.data == "start_trading":
        data["is_running"] = True
        await query.edit_message_text("🟢 تم تشغيل البوت بنجاح.", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

    elif query.data == "stop_trading":
        data["is_running"] = False
        await query.edit_message_text("🛑 تم إيقاف البوت.", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

    elif query.data == "check_status":
        await query.edit_message_text(
            f"📊 **حالة النظام:**\n• المصدر: `yfinance (GC=F)`\n• الإطار الزمني: `5 دقائق (M5)`\n• الرصيد: `{data['balance']:.2f}$`",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )

    elif query.data == "reset_balance":
        data["balance"] = 1000.0
        await query.edit_message_text("🔄 تم إعادة ضبط الرصيد إلى 1000$.", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

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
