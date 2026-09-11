import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from openai import OpenAI

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise RuntimeError("LINE environment variables are missing")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=25.0)

SYSTEM_INSTRUCTIONS = """
あなたはLINE上で動く『数値屋K_bot』です。
日本語で、簡潔で実用的に答えてください。
分からないことは推測で断定せず、必要なら確認質問をしてください。
このBotは現時点ではLINEで受け取ったテキストへの回答のみを行います。
ChatGPT本体のメモリ、過去チャット、Google Drive、GitHub等へ自動アクセスできるとは言わないでください。
""".strip()


@app.route("/", methods=["GET"])
def index():
    return "OK", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        app.logger.warning("Invalid LINE signature: %s", e)
        abort(400)
    except Exception:
        app.logger.exception("Unhandled callback error")
        abort(500)

    return "OK", 200


def generate_ai_reply(user_msg: str) -> str:
    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=user_msg,
        max_output_tokens=700,
    )

    text = (response.output_text or "").strip()
    if not text:
        return "うまく回答を生成できませんでした。もう一度送ってください。"

    # LINE text messages have a size limit, so leave some margin.
    return text[:4500]


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = (event.message.text or "").strip()
    app.logger.info("Text message received")

    if not user_msg:
        reply_text = "文字を入力して送ってください。"
    elif user_msg.lower() in {"/ping", "ping"}:
        reply_text = "pong"
    else:
        try:
            reply_text = generate_ai_reply(user_msg)
        except Exception:
            app.logger.exception("OpenAI request failed")
            reply_text = "AIへの接続でエラーが発生しました。少し待ってからもう一度送ってください。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text),
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
