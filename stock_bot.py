import os
import json
from flask import Flask, request
import yfinance as yf
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage
from cachetools import TTLCache

app = Flask(__name__)

# 快取設定：最多 100 筆，保留 300 秒 (5分鐘)
stock_cache = TTLCache(maxsize=100, ttl=300)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

WATCHLIST_FILE = "watchlist.json"

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["2330.TW", "2454.TW"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

# 核心計算與查詢函式（對應圖片中的本益比計算邏輯）
def get_stock_analysis(symbol):
    if symbol in stock_cache:
        return stock_cache[symbol]

    try:
        query_symbol = symbol + ".TW" if symbol.isdigit() and not symbol.endswith(".TW") else symbol
        stock = yf.Ticker(query_symbol)
        
        # 取得歷史股價（今日收盤價）
        history = stock.history(period="1d")
        if history.empty:
            return f"找不到代號 {symbol} 的資料。"
        current_price = history['Close'].iloc[-1]
        
        # 嘗試從 yfinance 取得近四季 EPS (Trailing EPS) 與 本益比 (Trailing PE)
        info = stock.info
        eps = info.get('trailingEps', None)
        pe_ratio = info.get('trailingPE', None)
        
        # 如果 yfinance 抓不到現成的 EPS，改從財報季報加總
        if not eps or not pe_ratio:
            quarterly_earnings = stock.quarterly_earnings
            if quarterly_earnings is not None and not quarterly_earnings.empty and 'Earnings' in quarterly_earnings.columns:
                # 取最近 4 個季度的淨利或 EPS 加總（視 yfinance 回傳格式而定）
                recent_eps = quarterly_earnings['Earnings'].iloc[-4:].sum()
                eps = recent_eps if recent_eps > 0 else 1.0
            else:
                eps = 0.0

        if not pe_ratio and eps > 0:
            pe_ratio = current_price / eps
        elif not pe_ratio:
            pe_ratio = 0.0

        # 計算近四季 EPS 加總與本益比對應
        # 依據你的公式：股價 / 近四季 EPS 加總 = 本益比
        calculated_eps_sum = current_price / pe_ratio if pe_ratio > 0 else eps
        
        result_msg = (
            f"📈 【{query_symbol.upper()} 估值分析】\n"
            f"• 今日收盤價：{current_price:.2f}\n"
            f"• 近四季 EPS 加總：{calculated_eps_sum:.2f}\n"
            f"• 計算本益比：{pe_ratio:.1f}\n"
            f"  (計算方式: {current_price:.2f} ÷ {calculated_eps_sum:.2f} = {pe_ratio:.1f})"
        )
        
        stock_cache[symbol] = result_msg
        return result_msg
    except Exception as e:
        return f"暫時無法取得 {symbol} 計算數據，請稍後再試。"

def get_stock_list():
    watchlist = load_watchlist()
    if not watchlist:
        return "目前清單是空的。"
    
    result = "📊 目前追蹤清單與本益比分析：\n"
    for symbol in watchlist:
        result += f"\n{get_stock_analysis(symbol)}\n"
    return result.strip()

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    try:
        data = json.loads(body)
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                user_text = event['message']['text'].strip()
                reply_token = event['replyToken']
                
                watchlist = load_watchlist()
                response_msg = ""

                if user_text == "清單":
                    response_msg = get_stock_list()
                elif user_text.startswith("新增 "):
                    new_symbol = user_text.replace("新增 ", "").strip().upper()
                    if not new_symbol.endswith(".TW") and new_symbol.isdigit():
                        new_symbol += ".TW"
                    if new_symbol not in watchlist:
                        watchlist.append(new_symbol)
                        save_watchlist(watchlist)
                        response_msg = f"✅ 成功新增 {new_symbol} 到清單！"
                    else:
                        response_msg = f"⚠️ {new_symbol} 已經在清單中了。"
                elif user_text.startswith("刪除 "):
                    del_symbol = user_text.replace("刪除 ", "").strip().upper()
                    if not del_symbol.endswith(".TW") and del_symbol.isdigit():
                        del_symbol += ".TW"
                    matched = [s for s in watchlist if s.upper() == del_symbol or s.split('.')[0] == del_symbol.split('.')[0]]
                    if matched:
                        for m in matched:
                            watchlist.remove(m)
                        save_watchlist(watchlist)
                        response_msg = f"🗑️ 成功從清單移除 {del_symbol}！"
                    else:
                        response_msg = f"⚠️ 找不到 {del_symbol}。"
                else:
                    response_msg = get_stock_analysis(user_text)

                line_bot_api.reply_message(reply_token, TextSendMessage(text=response_msg))
    except Exception as e:
        print(f"Error: {e}")

    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)