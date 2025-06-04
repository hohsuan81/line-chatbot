from flask import Flask, request, abort
from linebot.v3 import WebhookParser
from linebot.v3.messaging import MessagingApi, ReplyMessageRequest, TextMessage, PushMessageRequest
from linebot.v3.messaging import Configuration, ApiClient
from apscheduler.schedulers.background import BackgroundScheduler

import os
import sqlite3
from datetime import datetime

app = Flask(__name__)

# 建立 APScheduler 排程器
scheduler = BackgroundScheduler()

# 把這裡的 Channel Access Token 和 Secret 換成你自己的
channel_access_token = 'MVLD4+R4qzkb2QRUFCyYwO/ZP0vS84eZYjxDQkOLZpagFszusQUHpB01Woz50bU0uVAZNy4MOUeMqtc02OmLq+vH1ke6UdPOB2ipO9LqC0O1w/ZS6jaQi4xe88i+yS4vxHEKsaeI+35wv8cJmogpJAdB04t89/1O/w1cDnyilFU='
channel_secret = 'c00b5bc4269190998e8e5e1bde9f9e6b'

configuration = Configuration(access_token=channel_access_token)

# parser 負責驗證簽名
parser = WebhookParser(channel_secret)

# 初始化 SQLite 資料庫
def init_db():
    conn = sqlite3.connect("food_records.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            food_name TEXT,
            expiry_date TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        events = parser.parse(body, signature)
    except Exception as e:
        abort(400)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        for event in events:
            if event.type == "message" and event.message.type == "text":
                reply_token = event.reply_token
                user_text = event.message.text
                user_id = event.source.user_id

                # 嘗試解析輸入格式為「食物名稱 yyyy-mm-dd」
                try:
                    parts = user_text.strip().split()
                    if len(parts) != 2:
                        raise ValueError("格式錯誤")

                    food_name = parts[0]
                    expiry_date = datetime.strptime(parts[1], "%Y-%m-%d").date()

                    # 儲存到資料庫
                    conn = sqlite3.connect("food_records.db")
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO foods (user_id, food_name, expiry_date, created_at)
                        VALUES (?, ?, ?, ?)
                    ''', (user_id, food_name, expiry_date.isoformat(), datetime.now().isoformat()))
                    conn.commit()
                    conn.close()

                    reply_text = f"✅ 已記錄：{food_name}，有效期限為 {expiry_date}。"
                except Exception as e:
                    reply_text = "❌ 請用正確格式輸入，例如：\n牛奶 2025-06-10"

                message = TextMessage(text=reply_text)
                req = ReplyMessageRequest(reply_token=reply_token, messages=[message])
                line_bot_api.reply_message(req)

    return 'OK'

# 每日提醒任務（早上 9:00 執行）
@scheduler.scheduled_job('cron', minute='*/1')
def daily_expiry_reminder():
    print("⌛ 執行每日到期提醒")
    
    conn = sqlite3.connect("food_records.db")
    c = conn.cursor()
    c.execute('''
        SELECT user_id, food_name, expiry_date
        FROM foods
        WHERE DATE(expiry_date) <= DATE('now', '+3 days')
        ORDER BY user_id, expiry_date
    ''')
    rows = c.fetchall()
    conn.close()

    # 整理每個使用者的提醒清單
    from collections import defaultdict
    user_foods = defaultdict(list)
    for user_id, name, date in rows:
        user_foods[user_id].append(f"• {name}（{date}）")

    # 傳送提醒訊息給每個使用者
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        for user_id, foods in user_foods.items():
            text = "🔔 每日提醒：以下食物即將過期\n" + "\n".join(foods)
            req = PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
            line_bot_api.push_message(req)

# 啟動排程器
scheduler.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
