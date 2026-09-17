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
from openai import OpenAI  # استيراد مكتبة OpenAI الرسمية

# ==========================================
# 1. إعدادات خادم Flask ومفاتيح الذكاء الاصطناعي
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot is running with LLM AI Engine 24/7!"

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

# مفتاح OpenAI API (قم بوضعه هنا أو كمتبيعة بيئية Environment Variable)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "ضع_مفتاح_أوبن_آي_هنا").strip()
client = OpenAI(api_key=OPENAI_API_KEY)

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
# 2. واجهة الأزرار التفاعلية
# ==========================================
def main_menu_keyboard(source="twelvedata", timeframe="5min", ai_mode=True):
    is_active = check_source_status(source)
    status_icon = "🟢 نشط" if is_active else "🔴 غير نشط"
    source_name = "Twelve Data" if source == "twelvedata" else "yfinance"
    tf_names = {"1min": "1 دقيقة (M1)", "5min": "5 دقائق (M5)", "15min": "15 دقيقة (M15)"}
    tf_display = tf_names.get(timeframe, "5 دقائق (M5)")
    ai_icon = "🤖 خبير LLM مفعل" if ai_mode else "⚙️ إعدادات تقليدية"
    
    keyboard = [
        [
            InlineKeyboardButton("▶️ تشغيل التداول الذكي", callback_data="start_trading"),
            InlineKeyboardButton("⏹️ إيقاف التداول", callback_data="stop_trading")
        ],
        [
            InlineKeyboardButton(f"⚙️ المصدر: {source_name} ({status_icon})", callback_data="toggle_source"),
            InlineKeyboardButton(f"⏱️ الفريم: {tf_display}", callback_data="timeframe_menu")
        ],
        [
            InlineKeyboardButton(f"🧠 وضع الذكاء: {ai_icon}", callback_data="toggle_ai"),
            InlineKeyboardButton("💵 تعديل مبلغ الصفقة", callback_data="change_stake_menu")
        ],
        [
            InlineKeyboardButton("📊 حالة الحساب وعداد API", callback_data="check_status"),
            InlineKeyboardButton("🔄 إعادة ضبط الرصيد (1000$)", callback_data="reset_balance")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def timeframe_selection_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("⚡ دقيقة واحدة (M1)", callback_data="set_tf_1min"),
            InlineKeyboardButton("⚡ 5 دقائق (M5)", callback_data="set_tf_5min"),
            InlineKeyboardButton("⚡ 15 دقيقة (M15)", callback_data="set_tf_15min")
        ],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]
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
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==========================================
# 3. التحليل الفني مع تكامل نموذج LLM
# ==========================================
def get_llm_trading_decision(indicators_data):
    """
    تقوم هذه الدالة بإرسال بيانات المؤشرات الفنية إلى نموذج OpenAI
    للحصول على قرار ذكي ومبرر (CALL / PUT / WAIT)
    """
    try:
        system_prompt = (
            "أنت خبير تداول آلي ومحلل أسواق مالية مخضرم، متخصص حصرياً في تداول الذهب الفوري (Spot Gold - XAU/USD). "
            "مهمتك تحليل البيانات الفنية الواردة إليك وإرجاع الإجابة بصيغة محددة جداً.\n"
            "الرجاء الرد حصرياً على شكل سطرين:\n"
            "السطر الأول: إما CALL أو PUT أو WAIT\n"
            "السطر الثاني: تحليل قصير ومباشر باللغة العربية يوضح سبب التوصية بناءً على المؤشرات."
        )

        user_prompt = (
            f"بيانات السوق الحالية للذهب:\n"
            f"- السعر الحالي: {indicators_data['price']}\n"
            f"- مؤشر RSI: {indicators_data['rsi']}\n"
            f"- مؤشر Stochastic: {indicators_data['stoch']}\n"
            f"- متوسط الحركة EMA50: {indicators_data['ema50']}\n"
            f"- متوسط الحركة EMA200: {indicators_data['ema200']}\n"
            f"- حد بولينجر العلوي: {indicators_data['upper']}\n"
            f"- حد بولينجر السفلي: {indicators_data['lower']}\n"
            f"- تقلبات السوق ATR: {indicators_data['atr']}\n"
            f"بناءً على هذه المعطيات، ما هو قرارك؟"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # أو gpt-4o حسب رغبتك
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=100
        )

        result_text = response.choices[0].message.content.strip()
        lines = result_text.split('\n')
        signal = lines[0].strip().upper()
        reason = lines[1] if len(lines) > 1 else "تحليل ذكي تلقائي"

        if signal not in ["CALL", "PUT"]:
            signal = "WAIT"

        return signal, reason

    except Exception as e:
        print(f"خطأ في الاتصال بنموذج LLM: {e}")
        return "WAIT", "خطأ في الاتصال بالذكاء الاصطناعي"

def get_market_signals(source="twelvedata", timeframe="5min", ai_mode=True):
    try:
        if source == "yfinance":
            yf_intervals = {"1min": "1m", "5min": "5m", "15min": "15m"}
            interval = yf_intervals.get(timeframe, "5m")
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="5d", interval=interval)
            if len(df) < 50:
                return "WAIT", 0, 0, 0, 0, "بيانات غير كافية"
            close, high, low = df['Close'], df['High'], df['Low']
        else:
            increment_api_counter()
            params = {"symbol": "GOLD", "interval": timeframe, "outputsize": 100, "apikey": TWELVE_DATA_API_KEY}
            response = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=10)
            data = response.json()

            if "values" not in data or len(data["values"]) < 50:
                increment_api_counter()
                params["symbol"] = "XAU/USD"
                response = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=10)
                data = response.json()
                if "values" not in data or len(data["values"]) < 50:
                    return "WAIT", 0, 0, 0, 0, "بيانات غير كافية"

            df = pd.DataFrame(data["values"]).iloc[::-1].reset_index(drop=True)
            close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

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

        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean().iloc[-1]

        # تجميع المؤشرات لإرسالها للنموذج
        indicators = {
            "price": round(current_price, 2),
            "rsi": round(current_rsi, 1),
            "stoch": round(stoch_k, 1),
            "ema50": round(ema50, 2),
            "ema200": round(ema200, 2),
            "upper": round(upper_band, 2),
            "lower": round(lower_band, 2),
            "atr": round(atr, 2)
        }

        if ai_mode and OPENAI_API_KEY and len(OPENAI_API_KEY) > 10:
            signal, reason = get_llm_trading_decision(indicators)
            return signal, current_price, current_rsi, stoch_k, ema200, reason
        else:
            # خوارزمية افتراضية احتياطية إذا تم إلغاء تفعيل الذكاء الاصطناعي
            signal = "CALL" if current_rsi <= 35 else ("PUT" if current_rsi >= 65 else "WAIT")
            return signal, current_price, current_rsi, stoch_k, ema200, "تحليل خوارزمي اعتيادي"

    except Exception as e:
        print(f"خطأ في التحليل: {e}")
        return "WAIT", 0, 0, 0, 0, "خطأ بالتحليل"

# ==========================================
# 4. حلقة التداول المباشرة
# ==========================================
async def trading_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    while data.get("is_running", False):
        source = data.get("data_source", "twelvedata")
        timeframe = data.get("timeframe", "5min")
        ai_mode = data.get("ai_mode", True)
        
        signal, price, rsi, stoch, ema200, reason = get_market_signals(source=source, timeframe=timeframe, ai_mode=ai_mode)
        stake = data.get("current_stake", 1.0)
        
        if signal in ["PUT", "CALL"]:
            action_text = "🟢 شراء قوي (BUY / CALL)" if signal == "CALL" else "🔴 بيع قوي (SELL / PUT)"
            tf_sleep_map = {"1min": 60, "5min": 300, "15min": 900}
            sleep_duration = tf_sleep_map.get(timeframe, 300)
            tf_display_text = {"1min": "دقيقة واحدة (M1)", "5min": "5 دقائق (M5)", "15min": "15 دقيقة (M15)"}.get(timeframe, "5 دقائق")
            
            entry_time_str = datetime.now().strftime("%H:%M:%S")
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🤖 **إشارة خبير الذكاء الاصطناعي (LLM) - GOLD Spot:**\n"
                    f"• **التوصية:** {action_text}\n"
                    f"• **تحليل النموذج:** *{reason}*\n"
                    f"• **⏰ وقت الدخول:** `{entry_time_str}`\n"
                    f"• **📍 سعر الدخول:** `{price:.2f}`\n"
                    f"• **💵 مبلغ الصفقة:** `{stake:.2f}$`\n"
                    f"• **مؤشر RSI:** {rsi:.1f} | **Stoch:** {stoch:.1f}\n\n"
                    f"⏱️ **المدة الموصى بها:** {tf_display_text}\n"
                    f"⏳ جاري متابعة النتيجة..."
                ),
                parse_mode="Markdown"
            )
            
            await asyncio.sleep(sleep_duration) 
            
            new_signal, new_price, _, _, _, _ = get_market_signals(source=source, timeframe=timeframe, ai_mode=ai_mode)
            exit_time_str = datetime.now().strftime("%H:%M:%S")
            is_win = (signal == "CALL" and new_price > price) or (signal == "PUT" and new_price < price)
            
            if is_win:
                data["balance"] += stake * 0.85
                data["current_stake"] = data["base_stake"]
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ **صفقة ناجحة!**\n• الخروج: `{exit_time_str}`\n• السعر الجديد: `{new_price:.2f}`\n• الرصيد: {data['balance']:.2f}$",
                    parse_mode="Markdown"
                )
            else:
                data["balance"] -= stake
                data["current_stake"] *= 2.0
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ **صفقة خاسرة!**\n• الخروج: `{exit_time_str}`\n• السعر الجديد: `{new_price:.2f}`\n• الرصيد: {data['balance']:.2f}$\n• المضاعفة القادمة: {data['current_stake']:.2f}$",
                    parse_mode="Markdown"
                )
                
        await asyncio.sleep(20)

# ==========================================
# 5. المعالجات والأوامر
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    if "balance" not in data:
        data["balance"] = 1000.0
        data["base_stake"] = 1.0
        data["current_stake"] = 1.0
        data["is_running"] = False
        data["data_source"] = "twelvedata"
        data["timeframe"] = "5min"
        data["ai_mode"] = True

    await update.message.reply_text(
        "👋 **أهلاً بك في بوت إشارات الذهب المدعوم بنموذج الذكاء الاصطناعي (LLM)!**\n\n"
        "🎯 النظام الآن يرسل المؤشرات للذكاء الاصطناعي لتحليلها وإعطاء أسباب التوصية.\n"
        "استخدم الأزرار أدناه للتحكم:",
        reply_markup=main_menu_keyboard(data["data_source"], data["timeframe"], data["ai_mode"]),
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
        data["timeframe"] = "5min"
        data["ai_mode"] = True

    source, timeframe, ai_mode = data.get("data_source", "twelvedata"), data.get("timeframe", "5min"), data.get("ai_mode", True)

    if query.data == "toggle_source":
        new_source = "yfinance" if source == "twelvedata" else "twelvedata"
        data["data_source"] = new_source
        await query.edit_message_text(f"🔄 تم تغيير المصدر إلى: `{new_source}`", reply_markup=main_menu_keyboard(new_source, timeframe, ai_mode), parse_mode="Markdown")

    elif query.data == "toggle_ai":
        data["ai_mode"] = not ai_mode
        await query.edit_message_text(f"🧠 وضع الذكاء الاصطناعي: `{'مفعل' if data['ai_mode'] else 'معطل'}`", reply_markup=main_menu_keyboard(source, timeframe, data["ai_mode"]), parse_mode="Markdown")

    elif query.data == "timeframe_menu":
        await query.edit_message_text("⏱️ اختر الإطار الزمني:", reply_markup=timeframe_selection_keyboard(), parse_mode="Markdown")

    elif query.data.startswith("set_tf_"):
        tf_code = query.data.replace("set_tf_", "")
        data["timeframe"] = tf_code
        await query.edit_message_text(f"✅ تم تغيير الفريم إلى: `{tf_code}`", reply_markup=main_menu_keyboard(source, tf_code, ai_mode), parse_mode="Markdown")

    elif query.data == "start_trading":
        if data.get("is_running", False):
            await query.edit_message_text("⚠️ البوت يعمل بالفعل!", reply_markup=main_menu_keyboard(source, timeframe, ai_mode), parse_mode="Markdown")
        else:
            data["is_running"] = True
            await query.edit_message_text("🟢 تم تشغيل بوت التداول الذكي (LLM)...", reply_markup=main_menu_keyboard(source, timeframe, ai_mode), parse_mode="Markdown")
            asyncio.create_task(trading_loop(chat_id, context))

    elif query.data == "stop_trading":
        data["is_running"] = False
        await query.edit_message_text("🛑 تم إيقاف التداول.", reply_markup=main_menu_keyboard(source, timeframe, ai_mode), parse_mode="Markdown")

    elif query.data == "change_stake_menu":
        await query.edit_message_text("💵 اختر مبلغ الصفقة:", reply_markup=stake_selection_keyboard(), parse_mode="Markdown")

    elif query.data.startswith("set_stake_"):
        new_val = float(query.data.split("_")[-1])
        data["base_stake"], data["current_stake"] = new_val, new_val
        await query.edit_message_text(f"✅ تم تعديل مبلغ الصفقة إلى: {new_val}$", reply_markup=main_menu_keyboard(source, timeframe, ai_mode), parse_mode="Markdown")

    elif query.data == "main_menu":
        await query.edit_message_text("👋 القائمة الرئيسية:", reply_markup=main_menu_keyboard(source, timeframe, ai_mode), parse_mode="Markdown")

    elif query.data == "check_status":
        await query.edit_message_text(f"📊 الرصيد الحالي: {data['balance']:.2f}$\n🤖 الذكاء الاصطناعي: `{'مفعل' if ai_mode else 'معطل'}`", reply_markup=main_menu_keyboard(source, timeframe, ai_mode), parse_mode="Markdown")

    elif query.data == "reset_balance":
        data["balance"], data["base_stake"], data["current_stake"] = 1000.0, 1.0, 1.0
        await query.edit_message_text("🔄 تمت إعادة ضبط الرصيد إلى 1000$", reply_markup=main_menu_keyboard(source, timeframe, ai_mode), parse_mode="Markdown")

def main():
    keep_alive()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 البوت متصل بنموذج LLM وجاهز...")
    application.run_polling()

if __name__ == '__main__':
    main()
