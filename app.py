from flask import Flask, request, abort
from flask import jsonify
from linebot.v3 import WebhookParser
from linebot.v3.messaging import MessagingApi, ReplyMessageRequest, TextMessage, PushMessageRequest
from linebot.v3.messaging import Configuration, ApiClient

import os
import psycopg2
from datetime import datetime
from collections import defaultdict, timedelta

app = Flask(__name__)

# 把這裡的 Channel Access Token 和 Secret 換成你自己的
channel_access_token = 'MVLD4+R4qzkb2QRUFCyYwO/ZP0vS84eZYjxDQkOLZpagFszusQUHpB01Woz50bU0uVAZNy4MOUeMqtc02OmLq+vH1ke6UdPOB2ipO9LqC0O1w/ZS6jaQi4xe88i+yS4vxHEKsaeI+35wv8cJmogpJAdB04t89/1O/w1cDnyilFU='
channel_secret = 'c00b5bc4269190998e8e5e1bde9f9e6b'

configuration = Configuration(access_token=channel_access_token)

# parser 負責驗證簽名
parser = WebhookParser(channel_secret)

def get_connection():
    db_url = os.environ.get("DATABASE_URL")
    return psycopg2.connect(db_url)

# 建立資料表（如果還沒有）
def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS foods (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            food_name TEXT,
            expiry_date DATE,
            created_at TIMESTAMP
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

                    conn = get_connection()
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO foods (user_id, food_name, expiry_date, created_at)
                        VALUES (%s, %s, %s, %s)
                    ''', (user_id, food_name, expiry_date, datetime.now()))
                    conn.commit()
                    conn.close()

                    reply_text = f"✅ 已記錄：{food_name}，有效期限為 {expiry_date}。"
                except Exception as e:
                    reply_text = "❌ 請用正確格式輸入，例如：\n牛奶 2025-06-10"

                message = TextMessage(text=reply_text)
                req = ReplyMessageRequest(reply_token=reply_token, messages=[message])
                line_bot_api.reply_message(req)

    return 'OK'

def daily_expiry_reminder():
    print("⌛ 執行每日到期提醒")
    
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT user_id, food_name, expiry_date
        FROM foods
        WHERE expiry_date <= %s
        ORDER BY user_id, expiry_date
    ''', (datetime.now().date() + timedelta(days=3),))
    rows = c.fetchall()
    conn.close()

    # 整理每個使用者的提醒清單
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

@app.route("/run-reminder", methods=["GET"])
def run_reminder():
    try:
        daily_expiry_reminder()
        return jsonify({"status": "success", "message": "Reminder executed."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
