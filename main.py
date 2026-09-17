import asyncio
import logging
import os
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
# 2. الإعدادات وتوكن التليجرام ومفتاح API
# ==========================================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = "8916738723:AAG8YR35bIX-90HGUdjllwjGkiqbongI9lk"
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "C8c6abe66da242369986f71fd1cac414")

# ==========================================
# 3. لوحة الأزرار التفاعلية (مع زر التبديل بين المصادر)
# ==========================================
def main_menu_keyboard(source="twelvedata"):
    source_btn_text = "⚡ المصدر: Twelve Data" if source == "twelvedata" else "📈 المصدر: yfinance"
    keyboard = [
        [
            InlineKeyboardButton("▶️ تشغيل التداول المتقدم (M5)", callback_data="start_trading"),
            InlineKeyboardButton("⏹️ إيقاف التداول", callback_data="stop_trading")
        ],
        [
            InlineKeyboardButton(source_btn_text, callback_data="toggle_source"),
            InlineKeyboardButton("💵 تعديل مبلغ الصفقة", callback_data="change_stake_menu")
        ],
        [
            InlineKeyboardButton("📊 حالة الحساب والرصيد", callback_data="check_status"),
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
# 4. خوارزمية التحليل يدعم كلا المصدرين (Twelve Data / yfinance)
# ==========================================
def get_market_signals(source="twelvedata"):
    try:
        if source == "yfinance":
            # جلب البيانات من yfinance (رمز الذهب: GC=F)
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="5d", interval="5m")
            if len(df) < 50:
                print("تنبيه: البيانات الجالبة من yfinance غير كافية")
                return "WAIT", 0, 0, 0, 0, 0, 0, 0, ""
            
            close = df['Close']
            high = df['High']
            low = df['Low']
        else:
            # جلب البيانات من Twelve Data API (رمز الذهب: XAU/USD)
            url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=5min&outputsize=100&apikey={TWELVE_DATA_API_KEY}"
            response = requests.get(url, timeout=10)
            data = response.json()

            if "values" not in data or len(data["values"]) < 50:
                print(f"تنبيه Twelve Data: {data.get('message', 'No values returned')}")
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

        # ------------------------------------------
        # حساب قوة الإشارة (تصفية 60% فما فوق)
        # ------------------------------------------
        score = 0
        signal = "WAIT"

        # شروط إشارة الشراء (BUY / CALL)
        buy_conditions = [
            current_price > ema200 or current_price > ema50,
            current_rsi <= 40,
            stoch_k <= 35,
            current_price <= lower_band
        ]
        
        # شروط إشارة البيع (SELL / PUT)
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
        print(f"خطأ في التحليل: {e}")
        return "WAIT", 0, 0, 0, 0, 0, 0, 0, ""

# ==========================================
# 5. حلقة التداول المباشرة
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
            source_display = "Twelve Data ⚡" if source == "twelvedata" else "yfinance 📈"
            
            entry_time_str = datetime.now().strftime("%H:%M:%S")
            
            if signal == "CALL":
                entry_zone_str = f"{price:.2f} - {(price + 0.50):.2f}"
            else:
                entry_zone_str = f"{(price - 0.50):.2f} - {price:.2f}"
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🔥 **إشارة تداول جديدة (M5):**\n"
                    f"• **الزوج:** الذهب (XAU/USD)\n"
                    f"• **المصدر:** `{source_display}`\n"
                    f"• **التوصية:** {action_text}\n"
                    f"• **قوة الإشارة:** {strength_text}\n"
                    f"• **⏰ وقت الدخول:** `{entry_time_str}`\n"
                    f"• **📍 سعر / منطقة الدخول:** `{price:.2f}` *(نطاق: {entry_zone_str})*\n"
                    f"• **💵 مبلغ الصفقة:** `{stake:.2f}$`\n"
                    f"• **الاتجاه العام:** {trend_text}\n"
                    f"• **مؤشر RSI:** {rsi:.1f}\n"
                    f"• **مؤشر Stochastic:** {stoch:.1f}\n\n"
                    f"⏱️ **المدة الموصى بها على MT5:** 5 دقائق\n"
                    f"⏳ جاري متابعة الصفقة..."
                ),
                parse_mode="Markdown"
            )
            
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
# 6. المعالجات وأزرار التحكم
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
        "👋 **أهلاً بك في بوت إشارات الذهب المتقدم (M5)!**\n\n"
        "🎯 **الميزات:** التحويل بين مصادر البيانات + إشارات مؤكدة + إدارة مخاطر تفاعلية.\n"
        "استخدم الأزرار أدناه لتغيير المصدر أو التحكم بالبوت:",
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
        # التبديل بين المصدرين
        new_source = "yfinance" if source == "twelvedata" else "twelvedata"
        data["data_source"] = new_source
        source_name = "yfinance 📈" if new_source == "yfinance" else "Twelve Data ⚡"
        
        await query.edit_message_text(
            f"🔄 **تم تغيير مصدر البيانات بنجاح إلى:** `{source_name}`",
            reply_markup=main_menu_keyboard(new_source),
            parse_mode="Markdown"
        )

    elif query.data == "start_trading":
        if data.get("is_running", False):
            await query.edit_message_text(
                "⚠️ **البوت يعمل بالفعل حالياً!**",
                reply_markup=main_menu_keyboard(source),
                parse_mode="Markdown"
            )
        else:
            data["is_running"] = True
            source_display = "Twelve Data ⚡" if source == "twelvedata" else "yfinance 📈"
            await query.edit_message_text(
                f"🟢 **تم تشغيل تحليل الذهب المتقدم (M5)!**\n"
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
        status_text = "🟢 يعمل" if data.get("is_running", False) else "🔴 متوقف"
        source_display = "Twelve Data ⚡" if source == "twelvedata" else "yfinance 📈"
        await query.edit_message_text(
            f"📊 **حالة الحساب:**\n"
            f"• المصدر المعتمد: `{source_display}`\n"
            f"• الرصيد الحالي: {data['balance']:.2f}$\n"
            f"• مبلغ الصفقة الأساسي: {data['base_stake']:.2f}$\n"
            f"• حالة التداول: {status_text}",
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
# 7. نقطة الانطلاق
# ==========================================
def main():
    keep_alive()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("⚡ البوت المطور جاهز للعمل مع خيار تبديل المصادر...")
    application.run_polling()

if __name__ == '__main__':
    main()
