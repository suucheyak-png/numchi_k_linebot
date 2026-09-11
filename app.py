import os
import logging
import threading
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
openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0)

# v1: Renderプロセスが動いている間だけ保持する短期会話メモリ。
# 再デプロイ・再起動すると消えるため、永続保存用途には使わない。
conversation_state = {}
state_lock = threading.Lock()

SYSTEM_INSTRUCTIONS = """
あなたはLINE上で動く『数値屋K_bot』という個人向けAI秘書です。
日本語で、簡潔・実用的・数値重視に答えてください。

主な役割:
- 数値計算、比較、簡単なデータ分析
- 文章やメモの要約・整理・下書き
- タスクや予定の整理、優先順位づけ、手順化
- アイデア整理、意思決定の比較表現
- 会話の文脈を使った継続的な相談

回答方針:
- 結論を先に示し、必要なら理由や次の行動を続ける。
- 不明点は推測で断定せず、必要最小限の確認をする。
- ユーザーが送った数値は可能な限り具体的に計算・比較する。
- LINEで読みやすい長さ・改行にする。
- 外部サービスへの保存、予定登録、GitHub操作、Web検索などを実際に実行していない場合は、実行したとは言わない。
- ChatGPT本体のメモリや過去チャットへ自動アクセスできるとは言わない。
- このv1の会話記憶は短期記憶で、サーバー再起動や再デプロイで消える可能性がある。
""".strip()

HELP_TEXT = """数値屋K_bot v1 でできること

・質問・相談へのAI回答
・計算、比較、数値整理
・文章やメモの要約・下書き
・タスク整理、優先順位づけ
・同じ会話内で前の内容を踏まえた続きの相談

コマンド
/ping  接続確認
/reset 会話の短期記憶をリセット
/help  このヘルプ

※現時点では、予定登録や外部への永続保存はまだ自動実行しません。"""


@app.route("/", methods=["GET"])
def index():
    return "OK - numchi_k_linebot secretary v1", 200


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


def source_key(event) -> str:
    source = event.source
    user_id = getattr(source, "user_id", None)
    if user_id:
        return f"user:{user_id}"

    group_id = getattr(source, "group_id", None)
    if group_id:
        return f"group:{group_id}"

    room_id = getattr(source, "room_id", None)
    if room_id:
        return f"room:{room_id}"

    return "unknown"


def reset_conversation(key: str) -> None:
    with state_lock:
        conversation_state.pop(key, None)


def generate_ai_reply(key: str, user_msg: str) -> str:
    with state_lock:
        previous_response_id = conversation_state.get(key)

    kwargs = {
        "model": OPENAI_MODEL,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": user_msg,
        "max_output_tokens": 900,
    }
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id

    try:
        response = openai_client.responses.create(**kwargs)
    except Exception:
        # 直前のResponse IDが失効・不整合の場合は、1回だけ新規会話として再試行。
        if previous_response_id:
            app.logger.warning("Retrying OpenAI request without previous_response_id")
            kwargs.pop("previous_response_id", None)
            response = openai_client.responses.create(**kwargs)
        else:
            raise

    with state_lock:
        conversation_state[key] = response.id

    text = (response.output_text or "").strip()
    if not text:
        return "うまく回答を生成できませんでした。もう一度送ってください。"

    return text[:4500]


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = (event.message.text or "").strip()
    key = source_key(event)
    app.logger.info("Text message received: source=%s", key)

    command = user_msg.lower()

    if not user_msg:
        reply_text = "文字を入力して送ってください。"
    elif command in {"/ping", "ping"}:
        reply_text = "pong"
    elif command in {"/help", "help", "ヘルプ"}:
        reply_text = HELP_TEXT
    elif command in {"/reset", "reset", "リセット"}:
        reset_conversation(key)
        reply_text = "会話の短期記憶をリセットしました。新しい話題として始められます。"
    else:
        try:
            reply_text = generate_ai_reply(key, user_msg)
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
