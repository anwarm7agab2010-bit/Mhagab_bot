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

# ==========================================
# 1. خادم Flask لإبقاء البوت نشطاً 24/7
# ==========================================
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

# ==========================================
# 2. الإعدادات والتوكن ومفتاح API وعداد الطلبات
# ==========================================
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

# ==========================================
# 3. دالة فحص حالة المصدر
# ==========================================
def check_source_status(source="twelvedata"):
    if source == "twelvedata":
        return len(TWELVE_DATA_API_KEY) > 10
    else:
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="1d", interval="5m")
            return not df.empty
        except Exception:
            return False

# ==========================================
# 4. لوحة الأزرار التفاعلية (M5 SPOT GOLD)
# ==========================================
def main_menu_keyboard(source="twelvedata"):
    is_active = check_source_status(source)
    status_icon = "🟢 نشط" if is_active else "🔴 غير نشط"
    source_name = "Twelve Data" if source == "twelvedata" else "yfinance"
    
    source_btn_text = f"⚙️ المصدر: {source_name} ({status_icon})"
    
    keyboard = [
        [
            InlineKeyboardButton("▶️ تشغيل التداول المباشر (GOLD M5)", callback_data="start_trading"),
            InlineKeyboardButton("⏹️ إيقاف التداول", callback_data="stop_trading")
        ],
        [
            InlineKeyboardButton(source_btn_text, callback_data="toggle_source"),
            InlineKeyboardButton("💵 تعديل مبلغ الصفقة", callback_data="change_stake_menu")
        ],
        [
            InlineKeyboardButton("📊 حالة الحساب وعداد API", callback_data="check_status"),
            InlineKeyboardButton("🔄 إعادة ضبط الرصيد (1000$)", callback_data="reset_balance")
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
            InlineKeyboardButton("10$", callback_data="set_stake_10"),
            InlineKeyboardButton("20$", callback_data="set_stake_20"),
            InlineKeyboardButton("50$", callback_data="set_stake_50")
        ],
        [
            InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==========================================
# 5. خوارزمية التحليل لـ (Spot Gold M5)
# ==========================================
def get_market_signals(source="twelvedata"):
    try:
        if source == "yfinance":
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="5d", interval="5m")
            if len(df) < 50:
                return "WAIT", 0, 0, 0, 0, 0, 0, 0, ""
            
            close = df['Close']
            high = df['High']
            low = df['Low']
        else:
            increment_api_counter()
            params = {
                "symbol": "GOLD",
                "interval": "5min",
                "outputsize": 100,
                "apikey": TWELVE_DATA_API_KEY
            }
            response = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=10)
            data = response.json()

            if "values" not in data or len(data["values"]) < 50:
                increment_api_counter()
                params["symbol"] = "XAU/USD"
                response = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=10)
                data = response.json()
                if "values" not in data or len(data["values"]) < 50:
                    return "WAIT", 0, 0, 0, 0, 0, 0, 0, ""

            df = pd.DataFrame(data["values"]).iloc[::-1].reset_index(drop=True)
            close = df['close'].astype(float)
            high = df['high'].astype(float)
            low = df['low'].astype(float)

        current_price = close.iloc[-1]

        # 1. المتوسطات المتحركة (EMA 200 & EMA 50)
        ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1] if len(close) >= 200 else close.ewm(span=len(close), adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

        # 2. Bollinger Bands (20, 2)
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        upper_band = (sma20 + (2 * std20)).iloc[-1]
        lower_band = (sma20 - (2 * std20)).iloc[-1]

        # 3. RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        current_rsi = rsi_series.iloc[-1]

        # 4. Stochastic Oscillator (5, 3, 3)
        low_5 = low.rolling(window=5).min()
        high_5 = high.rolling(window=5).max()
        k_fast = 100 * ((close - low_5) / (high_5 - low_5))
        stoch_k = k_fast.rolling(window=3).mean().iloc[-1]

        # 5. MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = (macd_line - signal_line).iloc[-1]

        score = 0
        signal = "WAIT"

        buy_conditions = [
            current_price > ema200 or current_price > ema50,
            current_rsi <= 40,
            stoch_k <= 35,
            current_price <= lower_band
        ]
        
        sell_conditions = [
            current_price < ema200 or current_price < ema50,
            current_rsi >= 60,
            stoch_k >= 65,
            current_price >= upper_band
        ]

        if sum(buy_conditions) >= 2 and current_rsi <= 45:
            signal = "CALL"
            score = 60
            if current_price > ema200: score += 10
            if current_rsi <= 30: score += 10
            if current_rsi <= 20: score += 5
            if stoch_k <= 20: score += 5
            if current_price <= lower_band: score += 5
            if macd_hist > 0: score += 5

        elif sum(sell_conditions) >= 2 and current_rsi >= 55:
            signal = "PUT"
            score = 60
            if current_price < ema200: score += 10
            if current_rsi >= 70: score += 10
            if current_rsi >= 80: score += 5
            if stoch_k >= 80: score += 5
            if current_price >= upper_band: score += 5
            if macd_hist < 0: score += 5

        if signal in ["CALL", "PUT"] and score >= 60:
            if score >= 90:
                strength_text = f"⭐⭐⭐⭐⭐ {score}% (فائقة القوة 🚀)"
            elif score >= 80:
                strength_text = f"⭐⭐⭐⭐ {score}% (قوية جداً 💪)"
            elif score >= 70:
                strength_text = f"⭐⭐⭐ {score}% (قوية 👍)"
            else:
                strength_text = f"⭐⭐ {score}% (جيدة ⚡)"

            return signal, current_price, upper_band, lower_band, current_rsi, stoch_k, ema200, score, strength_text

        return "WAIT", current_price, upper_band, lower_band, current_rsi, stoch_k, ema200, 0, ""

    except Exception as e:
        print(f"خطأ في تحليل M5 SPOT GOLD: {e}")
        return "WAIT", 0, 0, 0, 0, 0, 0, 0, ""

# ==========================================
# 6. حلقة التداول المباشرة لصفقات M5
# ==========================================
async def trading_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    while data.get("is_running", False):
        source = data.get("data_source", "twelvedata")
        signal, price, upper, lower, rsi, stoch, ema200, score, strength_text = get_market_signals(source=source)
        stake = data.get("current_stake", 1.0)
        
        if signal in ["PUT", "CALL"] and score >= 60:
            action_text = "🟢 شراء قوي (BUY / CALL)" if signal == "CALL" else "🔴 بيع قوي (SELL / PUT)"
            trend_text = "صاعد 📈 (فوق EMA)" if signal == "CALL" else "هابط 📉 (تحت EMA)"
            source_display = "Twelve Data (GOLD Spot)" if source == "twelvedata" else "yfinance (GC=F)"
            
            entry_time_str = datetime.now().strftime("%H:%M:%S")
            
            if signal == "CALL":
                entry_zone_str = f"{price:.2f} - {(price + 0.50):.2f}"
            else:
                entry_zone_str = f"{(price - 0.50):.2f} - {price:.2f}"
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🔥 **إشارة تداول جديدة (GOLD Spot - M5):**\n"
                    f"• **الزوج:** Spot Gold Ounce vs USD (`GOLD` / `XAU/USD`)\n"
                    f"• **المصدر:** `{source_display}`\n"
                    f"• **التوصية:** {action_text}\n"
                    f"• **قوة الإشارة:** {strength_text}\n"
                    f"• **⏰ وقت الدخول:** `{entry_time_str}`\n"
                    f"• **📍 سعر / نطاق الدخول:** `{price:.2f}` *(نطاق: {entry_zone_str})*\n"
                    f"• **💵 مبلغ الصفقة:** `{stake:.2f}$`\n"
                    f"• **الاتجاه العام:** {trend_text}\n"
                    f"• **مؤشر RSI:** {rsi:.1f}\n"
                    f"• **مؤشر Stochastic:** {stoch:.1f}\n\n"
                    f"⏱️ **المدة الموصى بها على MT5:** 5 دقائق (M5)\n"
                    f"⏳ جاري متابعة الصفقة..."
                ),
                parse_mode="Markdown"
            )
            
            # الانتظار لمدة 5 دقائق (300 ثانية)
            await asyncio.sleep(300) 
            
            _, new_price, _, _, _, _, _, _, _ = get_market_signals(source=source)
            exit_time_str = datetime.now().strftime("%H:%M:%S")
            
            is_win = (signal == "CALL" and new_price > price) or (signal == "PUT" and new_price < price)
            
            if is_win:
                data["balance"] += stake * 0.85
                data["current_stake"] = data["base_stake"]
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ **صفقة ناجحة (M5)!**\n"
                        f"• ⏰ وقت الخروج: `{exit_time_str}`\n"
                        f"• 📍 سعر الدخول: `{price:.2f}`\n"
                        f"• 🏁 سعر الإغلاق: `{new_price:.2f}`\n"
                        f"• 💰 الرصيد الحالي: {data['balance']:.2f}$"
                    ),
                    parse_mode="Markdown"
                )
            else:
                data["balance"] -= stake
                data["current_stake"] *= 2.0
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"❌ **صفقة خاسرة (M5)!**\n"
                        f"• ⏰ وقت الخروج: `{exit_time_str}`\n"
                        f"• 📍 سعر الدخول: `{price:.2f}`\n"
                        f"• 🏁 سعر الإغلاق: `{new_price:.2f}`\n"
                        f"• 💰 الرصيد الحالي: {data['balance']:.2f}$\n"
                        f"• 🔄 قيمة الصفقة القادمة: {data['current_stake']:.2f}$"
                    ),
                    parse_mode="Markdown"
                )
                
        await asyncio.sleep(30)

# ==========================================
# 7. المعالجات والأوامر
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    if "balance" not in data:
        data["balance"] = 1000.0
        data["base_stake"] = 1.0
        data["current_stake"] = 1.0
        data["is_running"] = False
        data["data_source"] = "twelvedata"

    await update.message.reply_text(
        "👋 **أهلاً بك في بوت إشارات الذهب المباشرة (SPOT GOLD M5)!**\n\n"
        "🎯 **الزوج:** Spot Gold Ounce vs US Dollar (`GOLD` / `XAU/USD`)\n"
        "⏱️ **الإطار الزمني:** 5 دقائق (M5)\n"
        "استخدم الأزرار أدناه للتحكم بجميع الخيارات:",
        reply_markup=main_menu_keyboard(data["data_source"]),
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
        data["data_source"] = "twelvedata"

    source = data.get("data_source", "twelvedata")

    if query.data == "toggle_source":
        new_source = "yfinance" if source == "twelvedata" else "twelvedata"
        data["data_source"] = new_source
        is_active = check_source_status(new_source)
        status_str = "🟢 نشط ومتصل" if is_active else "🔴 غير نشط حالياً"
        source_name = "yfinance 📈" if new_source == "yfinance" else "Twelve Data ⚡"
        
        await query.edit_message_text(
            f"🔄 **تم تغيير مصدر البيانات إلى:** `{source_name}`\n• **حالة المصدر:** {status_str}",
            reply_markup=main_menu_keyboard(new_source),
            parse_mode="Markdown"
        )

    elif query.data == "start_trading":
        if data.get("is_running", False):
            await query.edit_message_text(
                "⚠️ **البوت يعمل بالفعل حالياً على M5!**",
                reply_markup=main_menu_keyboard(source),
                parse_mode="Markdown"
            )
        else:
            data["is_running"] = True
            is_active = check_source_status(source)
            status_str = "🟢 نشط" if is_active else "🔴 غير نشط"
            source_display = f"{'Twelve Data (GOLD)' if source == 'twelvedata' else 'yfinance (GC=F)'} ({status_str})"
            
            await query.edit_message_text(
                f"🟢 **تم تشغيل تحليل SPOT GOLD M5!**\n"
                f"• المصدر النشط: `{source_display}`\n"
                f"• الرصيد الحالي: {data['balance']:.2f}$\n"
                f"• مبلغ الصفقة المحدد: {data['base_stake']:.2f}$",
                reply_markup=main_menu_keyboard(source),
                parse_mode="Markdown"
            )
            asyncio.create_task(trading_loop(chat_id, context))

    elif query.data == "stop_trading":
        data["is_running"] = False
        await query.edit_message_text(
            "🛑 **تم إيقاف التداول.**",
            reply_markup=main_menu_keyboard(source),
            parse_mode="Markdown"
        )

    elif query.data == "change_stake_menu":
        await query.edit_message_text(
            f"💵 **تعديل مبلغ الصفقة:**\n"
            f"• المبلغ الحالي: `{data['base_stake']:.2f}$`\n"
            f"اختر القيمة الجديدة أدناه:",
            reply_markup=stake_selection_keyboard(),
            parse_mode="Markdown"
        )

    elif query.data.startswith("set_stake_"):
        new_val = float(query.data.split("_")[-1])
        data["base_stake"] = new_val
        data["current_stake"] = new_val
        await query.edit_message_text(
            f"✅ **تم تعديل مبلغ الصفقة بنجاح إلى: {new_val:.2f}$**",
            reply_markup=main_menu_keyboard(source),
            parse_mode="Markdown"
        )

    elif query.data == "main_menu":
        await query.edit_message_text(
            "👋 **القائمة الرئيسية:**",
            reply_markup=main_menu_keyboard(source),
            parse_mode="Markdown"
        )

    elif query.data == "check_status":
        is_active = check_source_status(source)
        status_str = "🟢 نشط ومتصل" if is_active else "🔴 غير نشط"
        status_bot = "🟢 يعمل" if data.get("is_running", False) else "🔴 متوقف"
        source_display = "Twelve Data (GOLD Spot)" if source == "twelvedata" else "yfinance (GC=F)"
        
        used = API_COUNTER["used_today"]
        limit = API_COUNTER["max_daily"]
        remains = max(0, limit - used)
        pct = (used / limit) * 100 if limit > 0 else 0
        
        await query.edit_message_text(
            f"📊 **حالة الحساب والمصدر:**\n"
            f"• **الزوج المعتمد:** `Spot Gold Ounce vs USD`\n"
            f"• **الفريم:** `M5 (5 Minutes)`\n"
            f"• **المصدر:** `{source_display}`\n"
            f"• **حالة الاتصال المباشرة:** {status_str}\n"
            f"• **الرصيد الحالي:** {data['balance']:.2f}$\n"
            f"• **مبلغ الصفقة الأساسي:** {data['base_stake']:.2f}$\n"
            f"• **حالة التداول:** {status_bot}\n\n"
            f"📈 **عداد طلبات API (Twelve Data):**\n"
            f"• **المستهلك اليوم:** `{used} / {limit}` طلب\n"
            f"• **المتبقي اليوم:** `{remains}` طلب\n"
            f"• **نسبة الاستهلاك:** `{pct:.1f}%`",
            reply_markup=main_menu_keyboard(source),
            parse_mode="Markdown"
        )

    elif query.data == "reset_balance":
        data["balance"] = 1000.0
        data["base_stake"] = 1.0
        data["current_stake"] = 1.0
        await query.edit_message_text(
            "🔄 **تم إعادة ضبط الرصيد بنجاح إلى 1000.00$**",
            reply_markup=main_menu_keyboard(source),
            parse_mode="Markdown"
        )

# ==========================================
# 8. نقطة الانطلاق
# ==========================================
def main():
    keep_alive()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("⚡ البوت المطور يعمل على SPOT GOLD M5...")
    application.run_polling()

if __name__ == '__main__':
    main()
