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

STOCK_NAMES = {
    "2330.TW": "台積電", "2330": "台積電",
    "2454.TW": "聯發科", "2454": "聯發科",
    "00646.TW": "元大標普500", "00646": "元大標普500",
    "6189.TW": "豐藝", "6189": "豐藝",
    "3037.TW": "欣興", "3037": "欣興",
    "2317.TW": "鴻海", "2317": "鴻海"
}

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["2330.TW", "2454.TW"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

def get_stock_analysis(symbol):
    clean_symbol = symbol.upper().strip()
    if clean_symbol in stock_cache:
        return stock_cache[clean_symbol]

    try:
        query_symbol = clean_symbol + ".TW" if clean_symbol.isdigit() and not clean_symbol.endswith(".TW") else clean_symbol
        stock = yf.Ticker(query_symbol)
        
        stock_name = STOCK_NAMES.get(query_symbol, STOCK_NAMES.get(clean_symbol, query_symbol))
        
        # 取得今日收盤價
        history = stock.history(period="1d")
        if history.empty:
            return f"找不到代號 {clean_symbol} 的資料。"
        current_price = history['Close'].iloc[-1]
        
        # 精確抓取近四季 EPS 加總
        eps_sum = 0.0
        try:
            financials = stock.quarterly_financials
            # 尋找包含 "Basic EPS" 或 "Diluted EPS" 的列
            eps_row = None
            for row in financials.index:
                if 'EPS' in row or 'Basic EPS' in row or 'Diluted EPS' in row:
                    eps_row = financials.loc[row]
                    break
            
            if eps_row is not None and not eps_row.empty:
                # 取最近 4 個季度的數字加總
                recent_4_eps = eps_row.dropna().iloc[:4]
                eps_sum = float(recent_4_eps.sum())
        except:
            pass

        # 如果從財報抓不到，退回使用 info 內的 trailingEps
        if eps_sum <= 0:
            info = stock.info
            eps_sum = info.get('trailingEps', 0.0)

        # 計算本益比 (股價 / 近四季EPS加總)
        if eps_sum > 0:
            pe_ratio = current_price / eps_sum
        else:
            pe_ratio = 0.0
        
        result_msg = (
            f"📈 【{stock_name} ({query_symbol.upper()})】\n"
            f"• 今日收盤價：{current_price:.2f}\n"
            f"• 近四季 EPS 加總：{eps_sum:.2f}\n"
            f"• 計算本益比：{pe_ratio:.1f}\n"
            f"  (計算方式: {current_price:.2f} ÷ {eps_sum:.2f} = {pe_ratio:.1f})"
        )
        
        stock_cache[clean_symbol] = result_msg
        return result_msg
    except Exception as e:
        return f"暫時無法取得 {symbol} 計算數據，請稍後再試。"

def get_stock_list():
    watchlist = load_watchlist()
    if not watchlist:
        return "目前清單是空的。"
    
    result = "📊 目前追蹤清單與估值分析：\n"
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