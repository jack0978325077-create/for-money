import os
import json
from flask import Flask, request
import yfinance as yf
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage
from cachetools import TTLCache  # 加入快取機制

app = Flask(__name__)

# 設定快取：最多記住 100 筆資料，每筆資料保留 300 秒 (5分鐘)
stock_cache = TTLCache(maxsize=100, ttl=300)

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', ''))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET', ''))

WATCHLIST_FILE = "watchlist.json"

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["2330.TW", "2454.TW"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

def get_stock_info(symbol):
    # 先檢查快取裡面有沒有資料
    if symbol in stock_cache:
        return f"{stock_cache[symbol]} (快取資料)"

    try:
        query_symbol = symbol + ".TW" if symbol.isdigit() and not symbol.endswith(".TW") else symbol
        stock = yf.Ticker(query_symbol)
        history = stock.history(period="1d")
        
        if history.empty:
            return f"找不到 {symbol} 的資料。"
        
        price = history['Close'].iloc[-1]
        msg = f"股票 {query_symbol.upper()} 最新股價: {price:.2f}"
        
        # 存入快取
        stock_cache[symbol] = msg
        return msg
    except Exception as e:
        return f"暫時無法取得 {symbol} 資料，請稍後再試。"

def get_stock_list():
    watchlist = load_watchlist()
    result = "📊 目前追蹤清單：\n"
    for symbol in watchlist:
        # 使用上面的查詢函式，自動利用快取
        result += f"- {get_stock_info(symbol)}\n"
    return result.strip()

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    try:
        data = json.loads(body)
        for event in data.get('events', []):
            user_text = event['message']['text'].strip()
            reply_token = event['replyToken']
            
            if user_text == "清單":
                response_msg = get_stock_list()
            elif user_text.startswith("新增 "):
                # (新增邏輯不變)
                ...
            elif user_text.startswith("刪除 "):
                # (刪除邏輯不變)
                ...
            else:
                response_msg = get_stock_info(user_text)
            
            line_bot_api.reply_message(reply_token, TextSendMessage(text=response_msg))
    except Exception as e:
        print(f"Error: {e}")
    return 'OK'