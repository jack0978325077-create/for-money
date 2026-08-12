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
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f: return json.load(f)
    return ["2330.TW", "2454.TW", "00646.TW"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f: json.dump(watchlist, f, ensure_ascii=False, indent=4)

def get_stock_analysis(user_input):
    clean_input = user_input.strip()
    query_symbol = STOCK_MAPPING.get(clean_input, clean_input.upper())
    if not query_symbol.endswith(".TW") and query_symbol.isdigit(): query_symbol += ".TW"
    if query_symbol in stock_cache: return stock_cache[query_symbol]

    stock_name = STOCK_NAMES.get(query_symbol, clean_input)
    code = query_symbol.split('.')[0]

    # --- 強制執行查詢 ---
    try:
        stock = yf.Ticker(query_symbol)
        info = stock.info
        # 直接抓取官方提供的數據，最穩定
        price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
        eps = info.get('trailingEps') or 0.0
        pe = info.get('trailingPE') or 0.0
        
        # 強制計算邏輯
        if eps > 0 and pe == 0: pe = price / eps
        if pe > 0 and eps == 0: eps = price / pe

        if eps > 0 and price:
            result = f"📈 【{stock_name} ({query_symbol.upper()})】\n• 今日收盤價：{price:.2f}\n• 近四季 EPS 加總：{eps:.2f}\n• 本益比：{pe:.1f}\n  (計算方式: {price:.2f} ÷ {eps:.2f} = {pe:.1f})"
            stock_cache[query_symbol] = result
            return result
    except: pass

    # --- 備援機制 ---
    try:
        data = twstock.realtime.get(code)
        if data and 'realtime' in data:
            price = float(data['realtime']['latest_trade_price'])
            result = f"📈 【{stock_name} ({code})】\n• 今日收盤價：{price:.2f}\n• (暫無財報盈餘與本益比資料)"
            stock_cache[query_symbol] = result
            return result
    except: pass

    return f"暫時無法取得「{clean_input}」的數據。"

def get_stock_list():
    watchlist = load_watchlist()
    return "\n".join([get_stock_analysis(s) for s in watchlist])

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    try:
        data = json.loads(body)
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                user_text = event['message']['text'].strip()
                is_group = event['source']['type'] != 'user'
                if is_group:
                    if not any(m.get('isSelf', False) for m in event['message'].get('mention', {}).get('mentionees', [])): continue
                    if " " in user_text: user_text = user_text.split(" ", 1)[-1].strip()

                if user_text == "清單": response_msg = get_stock_list()
                elif user_text.startswith("新增 "):
                    target = user_text.replace("新增 ", "").strip()
                    new_s = STOCK_MAPPING.get(target, target.upper())
                    if not new_s.endswith(".TW") and new_s.isdigit(): new_s += ".TW"
                    save_watchlist(list(set(load_watchlist() + [new_s])))
                    response_msg = f"✅ 已更新清單"
                elif user_text.startswith("刪除 "):
                    target = user_text.replace("刪除 ", "").strip()
                    wl = load_watchlist()
                    new_wl = [s for s in wl if target not in s]
                    save_watchlist(new_wl)
                    response_msg = f"🗑️ 已刪除"
                else: response_msg = get_stock_analysis(user_text)
                line_bot_api.reply_message(event['replyToken'], TextSendMessage(text=response_msg))
    except Exception as e: print(f"Error: {e}")
    return 'OK'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))