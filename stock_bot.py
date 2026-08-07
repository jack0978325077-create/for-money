import yfinance as yf
import requests
from flask import Flask, request, abort

app = Flask(__name__)

# 你的 LINE Messaging API 資訊
CHANNEL_ACCESS_TOKEN = "2EYPTd//kUuJQMwrtAZpXdJFkAWDvKDqdaiESz0ien6cFqPXoQ4kTJ2qmFyZruvlezGrAgqR9qOMmraOd9LIwVV1HF3ZphsVIhmoF4z0og8uKEmSoudXWDPUxP+H3afKYCuceIuNcACa++YPvtUlHgdB04t89/1O/w1cDnyilFU="

# 預設的關注清單
WATCH_LIST = ['2330.TW', '2464.TW', '5434.TW']

def reply_line_message(reply_token, message):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    requests.post(url, headers=headers, json=payload)

def get_stock_info(symbol):
    try:
        # 如果使用者輸入的是純數字（例如 2330），自動補上 .TW
        if symbol.isdigit() and len(symbol) == 4:
            symbol = symbol + ".TW"
        elif not symbol.endswith(('.TW', '.TWO')):
            symbol = symbol.upper()

        stock = yf.Ticker(symbol)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        pe = info.get('trailingPE')
        
        if price is None:
            return f"找不到股票代號 {symbol} 的資料。"
        
        return f"📌 股票: {symbol}\n💰 現價: {price}\n📊 本益比 (PE): {pe}"
    except Exception as e:
        return f"查詢發生錯誤: {e}"

def get_watchlist_report():
    msg = "📊 關注清單本益比報告：\n"
    for symbol in WATCH_LIST:
        stock = yf.Ticker(symbol)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        pe = info.get('trailingPE')
        msg += f"\n- {symbol} | 價: {price} | PE: {pe}"
    return msg

# 接收 LINE 傳過來的 Webhook 事件
@app.route("/", methods=['POST'])
def callback():
    body = request.get_json()
    events = body.get('events', [])
    
    for event in events:
        if event['type'] == 'message' and event['message']['type'] == 'text':
            user_text = event['message']['text'].strip()
            reply_token = event['replyToken']
            
            # 判斷使用者的指令
            if user_text == "清單" or user_text == "關注清單":
                response_msg = get_watchlist_report()
            else:
                # 把使用者的輸入當作股票代號查詢
                response_msg = get_stock_info(user_text)
                
            reply_line_message(reply_token, response_msg)
            
    return 'OK'

if __name__ == "__main__":
    app.run(port=5000)