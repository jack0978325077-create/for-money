import os
import json
from flask import Flask, request
import yfinance as yf
import twstock
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage
from cachetools import TTLCache

app = Flask(__name__)

stock_cache = TTLCache(maxsize=100, ttl=300)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

WATCHLIST_FILE = "watchlist.json"

STOCK_MAPPING = {
    "台積電": "2330.TW", "2330": "2330.TW",
    "聯發科": "2454.TW", "2454": "2454.TW",
    "元大標普500": "00646.TW", "00646": "00646.TW",
    "元大台灣50": "0050.TW", "0050": "0050.TW",
    "豐藝": "6189.TW", "6189": "6189.TW",
    "欣興": "3037.TW", "3037": "3037.TW",
    "鴻海": "2317.TW", "2317": "2317.TW"
}

STOCK_NAMES = {
    "2330.TW": "台積電", "2454.TW": "聯發科",
    "00646.TW": "元大標普500", "0050.TW": "元大台灣50",
    "6189.TW": "豐藝", "3037.TW": "欣興", "2317.TW": "鴻海"
}

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["2330.TW", "2454.TW", "00646.TW"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

def get_stock_analysis(user_input):
    clean_input = user_input.strip()
    query_symbol = STOCK_MAPPING.get(clean_input, clean_input.upper())
    if not query_symbol.endswith(".TW") and query_symbol.isdigit():
        query_symbol += ".TW"

    if query_symbol in stock_cache:
        return stock_cache[query_symbol]

    stock_name = STOCK_NAMES.get(query_symbol, clean_input)
    
    try:
        stock = yf.Ticker(query_symbol)
        history = stock.history(period="1d")
        if not history.empty:
            current_price = history['Close'].iloc[-1]
            info = stock.info
            eps_sum = info.get('trailingEps', 0.0)
            
            # 嘗試補強 EPS 加總
            if eps_sum == 0.0:
                try:
                    financials = stock.quarterly_financials
                    eps_row = next((financials.loc[row] for row in financials.index if 'EPS' in row), None)
                    if eps_row is not None:
                        eps_sum = float(eps_row.dropna().iloc[:4].sum())
                except:
                    pass
            
            # 計算本益比
            pe_ratio = current_price / eps_sum if eps_sum > 0 else 0.0
            
            # 嚴格依照你要求的計算格式輸出
            result_msg = (
                f"📈 【{stock_name} ({query_symbol.upper()})】\n"
                f"• 今日收盤價：{current_price:.2f}\n"
                f"• 近四季 EPS 加總：{eps_sum:.2f}\n"
                f"• 本益比：{pe_ratio:.1f}\n"
                f"  (計算方式: {current_price:.2f} ÷ {eps_sum:.2f} = {pe_ratio:.1f})"
            )
            
            stock_cache[query_symbol] = result_msg
            return result_msg
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        return f"無法取得「{clean_input}」的數據。"

    return f"暫時無法取得「{clean_input}」的計算數據。"