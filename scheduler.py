from apscheduler.schedulers.background import BackgroundScheduler
from linebot.v3.messaging import (
    MessagingApi, TextMessage, PushMessageRequest, TemplateMessage,
    ButtonsTemplate, PostbackAction
)
from linebot.v3.messaging import Configuration, ApiClient

import psycopg2
import os
from datetime import datetime, timedelta
from collections import defaultdict

# 建立 APScheduler 排程器
scheduler = BackgroundScheduler()

channel_access_token = 'MVLD4+R4qzkb2QRUFCyYwO/ZP0vS84eZYjxDQkOLZpagFszusQUHpB01Woz50bU0uVAZNy4MOUeMqtc02OmLq+vH1ke6UdPOB2ipO9LqC0O1w/ZS6jaQi4xe88i+yS4vxHEKsaeI+35wv8cJmogpJAdB04t89/1O/w1cDnyilFU='
channel_secret = 'c00b5bc4269190998e8e5e1bde9f9e6b'

configuration = Configuration(access_token=channel_access_token)

def get_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

# 每日提醒任務（早上 9:00 執行）
@scheduler.scheduled_job('cron', hour=9, minute=0)
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
            food_name, expiry = foods.split("（")
            expiry = expiry.strip("）")
        
            # 建立按鈕訊息
            template = TemplateMessage(
                alt_text=f"{food_name} 即將過期",
                template=ButtonsTemplate(
                    title=food_name,
                    text=f"到期日：{expiry}",
                    actions=[
                        PostbackAction(
                            label="✅ 已吃完",
                            data=f"consumed::{food_name}::{expiry}"
                        )
                    ]
                )
            )
        try:
            req = PushMessageRequest(to=user_id, messages=[template])
            line_bot_api.push_message(req)
        except Exception as e:
            print("❌ 推播訊息失敗：", e)

# 啟動排程器
scheduler.start()