from flask import Flask, request, abort

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route("/callback", methods=["POST"])
def callback():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
