import os
import json
from flask import Flask, request
import yfinance as yf

app = Flask(__name__)

# 記錄清單的檔案名稱
WATCHLIST_FILE = "watchlist.json"

# 載入清單的函式
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["2330.TW", "2454.TW"]  # 預設初始清單

# 儲存清單的函式
def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

# 查詢單一股票資訊
def get_stock_info(symbol):
    try:
        # 如果使用者輸入沒帶 .TW，自動補上（可依需求調整）
        if not symbol.endswith(".TW") and symbol.isdigit():
            query_symbol = symbol + ".TW"
        else:
            query_symbol = symbol
            
        stock = yf.Ticker(query_symbol)
        history = stock.history(period="1d")
        if history.empty:
            return f"找不到代號 {symbol} 的資料。"
        
        current_price = history['Close'].iloc[-1]
        return f"股票 {query_symbol.upper()} 最新股價: {current_price:.2f}"
    except Exception as e:
        return f"查詢發生錯誤: {str(e)}"

# 查詢整份清單
def get_stock_list():
    watchlist = load_watchlist()
    if not watchlist:
        return "目前清單是空的。"
    
    result = "📊 目前追蹤清單：\n"
    for symbol in watchlist:
        try:
            stock = yf.Ticker(symbol)
            history = stock.history(period="1d")
            if not history.empty:
                price = history['Close'].iloc[-1]
                result += f"- {symbol}: {price:.2f}\n"
            else:
                result += f"- {symbol}: 無資料\n"
        except:
            result += f"- {symbol}: 查詢失敗\n"
    return result.strip()

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_json()
    # 這裡依據你的 LINE 事件結構抓取使用者訊息
    try:
        event = body['events'][0]
        user_text = event['message']['text'].strip()
        reply_token = event['replyToken']
    except:
        return 'OK'

    watchlist = load_watchlist()
    response_msg = ""

    # 1. 檢視清單
    if user_text == "清單":
        response_msg = get_stock_list()
        
    # 2. 新增股票（例如：新增 2330 或 新增 2330.TW）
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
            
    # 3. 刪除股票（例如：刪除 2330）
    elif user_text.startswith("刪除 "):
        del_symbol = user_text.replace("刪除 ", "").strip().upper()
        if not del_symbol.endswith(".TW") and del_symbol.isdigit():
            del_symbol += ".TW"
            
        # 嘗試移除（支援有無 .TW 的輸入比對）
        matched = [s for s in watchlist if s.upper() == del_symbol or s.split('.')[0] == del_symbol.split('.')[0]]
        if matched:
            for m in matched:
                watchlist.remove(m)
            save_watchlist(watchlist)
            response_msg = f"🗑️ 成功從清單移除 {del_symbol}！"
        else:
            response_msg = f"⚠️ 找不到 {del_symbol}。"
            
    # 4. 指定查詢單一股票（直接輸入代號）
    else:
        response_msg = get_stock_info(user_text)

    # 這裡呼叫你的 LINE 回傳函式 (reply_line_message)
    # reply_line_message(reply_token, response_msg)

    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)