from apscheduler.schedulers.background import BackgroundScheduler
from linebot.v3.messaging import MessagingApi, TextMessage, PushMessageRequest
from linebot.v3.messaging import Configuration, ApiClient

import os
import sqlite3
from datetime import datetime

# 建立 APScheduler 排程器
scheduler = BackgroundScheduler()

channel_access_token = 'MVLD4+R4qzkb2QRUFCyYwO/ZP0vS84eZYjxDQkOLZpagFszusQUHpB01Woz50bU0uVAZNy4MOUeMqtc02OmLq+vH1ke6UdPOB2ipO9LqC0O1w/ZS6jaQi4xe88i+yS4vxHEKsaeI+35wv8cJmogpJAdB04t89/1O/w1cDnyilFU='
channel_secret = 'c00b5bc4269190998e8e5e1bde9f9e6b'

configuration = Configuration(access_token=channel_access_token)

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