# app.py (最小構成 / 確実動作確認版)
import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# Flask設定
app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# 環境変数取得
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)


@app.route("/", methods=["GET"])
def index():
    return "OK", 200


@app.route("/callback", methods=["POST"])
def callback():
    # 確認ログ
    app.logger.info("=== CALLBACK TRIGGERED ===")

    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    app.logger.info(f"[callback] headers={dict(request.headers)}")
    app.logger.info(f"[callback] body={body}")

    # LINEシグネチャ検証
    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        app.logger.error(f"[callback] InvalidSignatureError: {e}")
        abort(400)
    except Exception as e:
        app.logger.error(f"[callback] Exception: {e}")
        abort(500)

    return "OK", 200


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    app.logger.info(f"[message] from={event.source.user_id}, text={user_msg}")
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"pong: {user_msg}")
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
