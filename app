from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 加入這段來處理使用者傳來的文字訊息
@handler.add(MessageEvent)
def handle_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text))

app = Flask(__name__)

line_bot_api = LineBotApi('MVLD4+R4qzkb2QRUFCyYwO/ZP0vS84eZYjxDQkOLZpagFszusQUHpB01Woz50bU0uVAZNy4MOUeMqtc02OmLq+vH1ke6UdPOB2ipO9LqC0O1w/ZS6jaQi4xe88i+yS4vxHEKsaeI+35wv8cJmogpJAdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('c00b5bc4269190998e8e5e1bde9f9e6b')

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'