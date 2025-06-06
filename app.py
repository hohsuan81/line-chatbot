from flask import Flask, request, abort
from flask import jsonify
from linebot.v3 import WebhookParser
from linebot.v3.messaging import MessagingApi, ReplyMessageRequest, TextMessage, PushMessageRequest
from linebot.v3.messaging import Configuration, ApiClient
from scheduler import daily_expiry_reminder

import os
import psycopg2
from datetime import datetime

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

def alter_table():
    try:
        conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
        cur = conn.cursor()
        cur.execute("ALTER TABLE foods ADD COLUMN IF NOT EXISTS is_consumed BOOLEAN")
        conn.commit()
        conn.close()
        print("資料表已更新")
    except Exception as e:
        print("跳過 ALTER TABLE：", e)

alter_table()

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

                if user_text == "分析":
                    conn = get_connection()
                    cursor = conn.cursor()

                    # 查詢使用者總共記錄了幾項食物，以及吃完幾項
                    cursor.execute('''
                        SELECT COUNT(*) FROM foods WHERE user_id = %s
                    ''', (user_id,))
                    total = cursor.fetchone()[0]

                    cursor.execute('''
                        SELECT COUNT(*) FROM foods WHERE user_id = %s AND is_consumed = TRUE
                    ''', (user_id,))
                    consumed = cursor.fetchone()[0]

                    conn.close()

                    if total == 0:
                        reply_text = "目前沒有任何食物紀錄喔 🍽️"
                    else:
                        rate = round(consumed / total * 100, 1)
                        reply_text = f"📊 消費分析\n你總共紀錄了 {total} 項食物，其中 {consumed} 項已吃完。\n➡️ 消耗率：{rate}%"

                elif user_text == "未吃完":
                    conn = get_connection()
                    cursor = conn.cursor()

                    cursor.execute('''
                        SELECT food_name, expiry_date FROM foods
                        WHERE user_id = %s AND is_consumed IS DISTINCT FROM TRUE
                        ORDER BY expiry_date
                    ''', (user_id,))
                    rows = cursor.fetchall()
                    conn.close()

                    if not rows:
                        reply_text = "🎉 沒有未吃完的食物了！"
                    else:
                        reply_text = "🍱 未吃完的食物清單：\n"
                        for name, date in rows:
                            reply_text += f"• {name}（{date}）\n"

                elif user_text.startswith("採買建議"):
                    parts = user_text.strip().split()

                    if len(parts) == 2:
                        target_food = parts[1]

                        conn = get_connection()
                        cur = conn.cursor()
                        cur.execute("""
                            SELECT COUNT(*) AS total,
                                SUM(CASE WHEN is_consumed THEN 1 ELSE 0 END) AS consumed,
                                ROUND(SUM(CASE WHEN is_consumed THEN 1 ELSE 0 END)::decimal / COUNT(*) * 100, 1) AS rate
                            FROM foods
                            WHERE user_id = %s AND food_name = %s
                        """, (user_id, target_food))

                        row = cur.fetchone()
                        conn.close()

                        total, consumed, rate = row
                        if total == 0:
                            reply_text = f"🔍 沒有找到 {target_food} 的食用紀錄喔！"
                        else:
                            if rate >= 80:
                                suggestion = "✓ 吃得很乾淨，建議可以維持或略增加份量"
                            elif 50 <= rate < 80:
                                suggestion = "✓ 建議維持目前購買量"
                            else:
                                suggestion = "⚠️ 常吃不完，建議下次減量購買"

                            reply_text = f"🛒「{target_food}」的採買建議：\n{suggestion}（消耗率 {rate}%）"
                    else:
                        reply_text = "❌ 請輸入格式：採買建議 食物名稱\n例如：採買建議 牛奶"


                else:
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

            elif event.type == "postback":
                data = event.postback.data
                if data.startswith("consumed::"):
                    try:
                        _, food_name, expiry_date = data.split("::")
                        user_id = event.source.user_id

                        conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
                        cur = conn.cursor()
                        cur.execute("""
                            UPDATE foods
                            SET is_consumed = TRUE
                            WHERE user_id = %s AND food_name = %s AND expiry_date = %s
                        """, (user_id, food_name, expiry_date))
                        conn.commit()
                        conn.close()

                        # 回覆使用者
                        reply_token = event.reply_token
                        message = TextMessage(text=f"✅ 已記錄你吃完了 {food_name}！")
                        req = ReplyMessageRequest(reply_token=reply_token, messages=[message])
                        line_bot_api.reply_message(req)
                    except Exception as e:
                        print("處理 postback 發生錯誤：", e)

    return 'OK'

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