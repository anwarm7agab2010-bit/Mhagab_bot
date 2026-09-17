import asyncio
import logging
import os
from datetime import datetime
import yfinance as yf
import pandas as pd
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
# 2. الإعدادات والتوكن
# ==========================================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = "8916738723:AAG8YR35bIX-90HGUdjllwjGkiqbongI9lk"

# ==========================================
# 3. لوحة الأزرار التفاعلية
# ==========================================
def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("▶️ تشغيل التداول المتقدم (M5)", callback_data="start_trading"),
            InlineKeyboardButton("⏹️ إيقاف التداول", callback_data="stop_trading")
        ],
        [
            InlineKeyboardButton("📊 حالة الحساب والرصيد", callback_data="check_status"),
            InlineKeyboardButton("🔄 إعادة ضبط الرصيد (1000$)", callback_data="reset_balance")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==========================================
# 4. خوارزمية التوافق واستخراج قوة الإشارة
# ==========================================
def get_market_signals(symbol="GC=F"):
    try:
        # جلب بيانات الذهب لآخر 5 أيام بإطار 5 دقائق
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="5m")
        
        if len(df) < 210:
            return "WAIT", 0, 0, 0, 0, 0, 0, ""

        close = df['Close']
        high = df['High']
        low = df['Low']

        # 1. حساب الاتجاه العام (EMA 200)
        ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]

        # 2. حساب Bollinger Bands (20, 2)
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        upper_band = (sma20 + (2 * std20)).iloc[-1]
        lower_band = (sma20 - (2 * std20)).iloc[-1]

        current_price = close.iloc[-1]

        # 3. حساب RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        current_rsi = rsi_series.iloc[-1]

        # 4. حساب Stochastic Oscillator (5, 3, 3)
        low_5 = low.rolling(window=5).min()
        high_5 = high.rolling(window=5).max()
        k_fast = 100 * ((close - low_5) / (high_5 - low_5))
        stoch_k = k_fast.rolling(window=3).mean().iloc[-1]

        # شروط الإشارة
        is_buy = (
            current_price > ema200 and
            current_price <= lower_band and
            current_rsi <= 35 and
            stoch_k <= 25
        )

        is_sell = (
            current_price < ema200 and
            current_price >= upper_band and
            current_rsi >= 65 and
            stoch_k >= 75
        )

        signal = "WAIT"
        strength_score = 75
        strength_text = ""

        if is_buy:
            signal = "CALL"
            if current_rsi <= 25: strength_score += 5
            if current_rsi <= 20: strength_score += 5
            if stoch_k <= 15: strength_score += 5
            if stoch_k <= 10: strength_score += 5
            if current_price < lower_band: strength_score += 4
            
        elif is_sell:
            signal = "PUT"
            if current_rsi >= 75: strength_score += 5
            if current_rsi >= 80: strength_score += 5
            if stoch_k >= 85: strength_score += 5
            if stoch_k >= 90: strength_score += 5
            if current_price > upper_band: strength_score += 4

        if signal in ["CALL", "PUT"]:
            if strength_score >= 90:
                strength_text = f"⭐⭐⭐⭐⭐ {strength_score}% (فائقة القوة 🚀)"
            elif strength_score >= 82:
                strength_text = f"⭐⭐⭐⭐ {strength_score}% (قوية جداً 💪)"
            else:
                strength_text = f"⭐⭐⭐ {strength_score}% (قوية 👍)"

            return signal, current_price, upper_band, lower_band, current_rsi, stoch_k, ema200, strength_text

        return "WAIT", current_price, upper_band, lower_band, current_rsi, stoch_k, ema200, ""

    except Exception as e:
        print(f"خطأ في تحليل البيانات: {e}")
        return "WAIT", 0, 0, 0, 0, 0, 0, ""

# ==========================================
# 5. حلقة التداول ومتابعة الصفقات
# ==========================================
async def trading_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    while data.get("is_running", False):
        signal, price, upper, lower, rsi, stoch, ema200, strength_text = get_market_signals("GC=F")
        stake = data.get("current_stake", 1.0)
        
        if signal in ["PUT", "CALL"]:
            action_text = "🟢 شراء قوي (BUY / CALL)" if signal == "CALL" else "🔴 بيع قوي (SELL / PUT)"
            trend_text = "صاعد 📈 (فوق EMA 200)" if signal == "CALL" else "هابط 📉 (تحت EMA 200)"
            
            # ⏰ استخراج وقت الدخول الحالي
            entry_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 📍 تحديد منطقة / نطاق الدخول المقترح
            if signal == "CALL":
                entry_zone_str = f"{price:.2f} - {(price + 0.50):.2f}"
            else:
                entry_zone_str = f"{(price - 0.50):.2f} - {price:.2f}"
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🔥 **إشارة تداول جديدة (M5):**\n"
                    f"• **الزوج:** الذهب (XAU/USD)\n"
                    f"• **التوصية:** {action_text}\n"
                    f"• **قوة الإشارة:** {strength_text}\n"
                    f"• **⏰ وقت الدخول:** `{entry_time_str}`\n"
                    f"• **📍 سعر / منطقة الدخول:** `{price:.2f}` *(نطاق: {entry_zone_str})*\n"
                    f"• **الاتجاه العام:** {trend_text}\n"
                    f"• **مؤشر RSI:** {rsi:.1f}\n"
                    f"• **مؤشر Stochastic:** {stoch:.1f}\n\n"
                    f"⏱️ **المدة الموصى بها على MT5:** 5 دقائق\n"
                    f"⏳ جاري مراقبة الصفقة..."
                ),
                parse_mode="Markdown"
            )
            
            # الانتظار لمدة 5 دقائق لمتابعة إغلاق الشمعة
            await asyncio.sleep(300) 
            
            # فحص سعر الإغلاق ووقت الإغلاق
            _, new_price, _, _, _, _, _, _ = get_market_signals("GC=F")
            exit_time_str = datetime.now().strftime("%H:%M:%S")
            
            # تقييم النتيجة
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
                
        # الانتظار 30 ثانية قبل الفحص القادم
        await asyncio.sleep(30)

# ==========================================
# 6. المعالجات والأوامر
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    if "balance" not in data:
        data["balance"] = 1000.0
        data["base_stake"] = 1.0
        data["current_stake"] = 1.0
        data["is_running"] = False

    await update.message.reply_text(
        "👋 **أهلاً بك في بوت إشارات الذهب المتقدم (M5)!**\n\n"
        "🎯 **الاستراتيجية الحالية:** EMA 200 + Bollinger + RSI + Stochastic\n"
        "استخدم الأزرار أدناه للتحكم في البوت:",
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

    if query.data == "start_trading":
        if data.get("is_running", False):
            await query.edit_message_text(
                "⚠️ **البوت يعمل بالفعل حالياً بالخوارزمية المتقدمة!**",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
        else:
            data["is_running"] = True
            await query.edit_message_text(
                f"🟢 **تم تشغيل تحليل الذهب المتقدم على فريم M5!**\n• الرصيد الحالي: {data['balance']:.2f}$",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
            asyncio.create_task(trading_loop(chat_id, context))

    elif query.data == "stop_trading":
        data["is_running"] = False
        await query.edit_message_text(
            "🛑 **تم إيقاف التداول.**",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )

    elif query.data == "check_status":
        status_text = "🟢 يعمل (الخوارزمية المتقدمة)" if data.get("is_running", False) else "🔴 متوقف"
        await query.edit_message_text(
            f"📊 **حالة الحساب:**\n"
            f"• الرصيد الافتراضي: {data['balance']:.2f}$\n"
            f"• قيمة الصفقة الحالية: {data.get('current_stake', 1.0):.2f}$\n"
            f"• حالة التداول: {status_text}",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )

    elif query.data == "reset_balance":
        data["balance"] = 1000.0
        data["current_stake"] = 1.0
        await query.edit_message_text(
            "🔄 **تم إعادة ضبط الرصيد بنجاح إلى 1000.00$**",
            reply_markup=main_menu_keyboard(),
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

    print("⚡ البوت المطور يتضمن وقت ومكان الدخول يعمل الآن...")
    application.run_polling()

if __name__ == '__main__':
    main()
