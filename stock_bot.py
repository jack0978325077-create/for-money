import os
import json
from flask import Flask, request
import yfinance as yf
import twstock
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage
from cachetools import TTLCache

app = Flask(__name__)
# 快取縮短為 60 秒，確保即時性
stock_cache = TTLCache(maxsize=100, ttl=60)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '')
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
WATCHLIST_FILE = "watchlist.json"

STOCK_MAPPING = {
    "台積電": "2330.TW", "2330": "2330.TW",
    "聯發科": "2454.TW", "2454": "2454.TW",
    "漢唐": "2404.TW", "2404": "2404.TW",
    "元大標普500": "00646.TW", "00646": "00646.TW",
    "元大台灣50": "0050.TW", "0050": "0050.TW",
    "豐藝": "6189.TW", "6189": "6189.TW",
    "欣興": "3037.TW", "3037": "3037.TW",
    "鴻海": "2317.TW", "2317": "2317.TW"
}

STOCK_NAMES = {
    "2330.TW": "台積電",
    "2454.TW": "聯發科",
    "2404.TW": "漢唐",
    "00646.TW": "元大標普500",
    "0050.TW": "元大台灣50",
    "6189.TW": "豐藝",
    "3037.TW": "欣興",
    "2317.TW": "鴻海"
}

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f: return json.load(f)
    return ["2330.TW", "2454.TW", "2404.TW", "00646.TW"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f: json.dump(watchlist, f, ensure_ascii=False, indent=4)

def get_stock_analysis(user_input):
    clean_input = user_input.strip()
    query_symbol = STOCK_MAPPING.get(clean_input, clean_input.upper())
    if not query_symbol.endswith(".TW") and query_symbol.isdigit(): query_symbol += ".TW"
    if query_symbol in stock_cache: return stock_cache[query_symbol]

    stock_name = STOCK_NAMES.get(query_symbol, clean_input)
    code = query_symbol.split('.')[0]
    
    price = 0.0
    eps_sum = 0.0

    # 1. 優先透過 twstock 抓取最即時、絕對不會失敗的盤中/收盤價
    try:
        data = twstock.realtime.get(code)
        if data and 'realtime' in data:
            price = float(data['realtime']['latest_trade_price'])
    except:
        pass

    # 如果 twstock 抓不到，改用 yfinance 抓股價
    if not price or price <= 0:
        try:
            stock = yf.Ticker(query_symbol)
            hist = stock.history(period="1d")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
        except:
            pass

    # 2. 即時計算 EPS（從 yfinance 財報季報即時加總近四季）
    try:
        stock = yf.Ticker(query_symbol)
        info = stock.info
        
        # 先嘗試直接從 info 拿 trailingEps
        eps_sum = info.get('trailingEps', 0.0)
        
        # 如果 info 沒有，從季報即時抓取前四個季度的 EPS 加總
        if not eps_sum or eps_sum == 0.0:
            financials = stock.quarterly_financials
            if financials is not None and not financials.empty:
                # 尋找包含 EPS 的列
                eps_row = next((financials.loc[row] for row in financials.index if 'EPS' in str(row).upper() or 'EARNINGS PER SHARE' in str(row).upper()), None)
                if eps_row is not None:
                    valid_eps = eps_row.dropna()
                    if len(valid_eps) >= 4:
                        eps_sum = float(valid_eps.iloc[:4].sum())
        
        # 如果還是沒有，嘗試用官方本益比(trailingPE)與現價反推 EPS
        if (not eps_sum or eps_sum == 0.0) and price > 0:
            pe_from_info = info.get('trailingPE', 0.0)
            if pe_from_info > 0:
                eps_sum = price / pe_from_info
    except:
        pass

    # 3. 輸出結果組合
    if price and price > 0:
        if eps_sum and eps_sum > 0:
            pe_ratio = price / eps_sum
            result = (
                f"📈 【{stock_name} ({query_symbol.upper()})】\n"
                f"• 今日收盤價：{price:.2f}\n"
                f"• 近四季 EPS 加總：{eps_sum:.2f}\n"
                f"• 本益比：{pe_ratio:.1f}\n"
                f"  (計算方式: {price:.2f} ÷ {eps_sum:.2f} = {pe_ratio:.1f})"
            )
        else:
            result = f"📈 【{stock_name} ({query_symbol.upper()})】\n• 今日收盤價：{price:.2f}\n• (暫無財報盈餘與本益比資料)"
        
        stock_cache[query_symbol] = result
        return result

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