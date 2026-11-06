from collections import OrderedDict, deque
from math import ceil
from threading import Lock
from time import monotonic

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import BadRequest

from services.llm_service import GeminiServiceError, generate_response

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1_000_000

MAX_HISTORY_MESSAGES = 20
MAX_USER_MESSAGE_CHARS = 4_000
MAX_ASSISTANT_MESSAGE_CHARS = 12_000
CHAT_RATE_LIMIT_REQUESTS = 10
CHAT_RATE_LIMIT_WINDOW_SECONDS = 60
MAX_RATE_LIMIT_CLIENTS = 1_024

# This bounded in-memory limiter suits the single-process local app; production
# deployments with multiple workers should use a shared rate-limit store.
_rate_limit_requests: OrderedDict[str, deque[float]] = OrderedDict()
_rate_limit_lock = Lock()


def _rate_limit_retry_after(client_id: str, now: float) -> int | None:
    with _rate_limit_lock:
        timestamps = _rate_limit_requests.get(client_id)
        if timestamps is None:
            timestamps = deque()
            _rate_limit_requests[client_id] = timestamps

        while (
            timestamps
            and now - timestamps[0] >= CHAT_RATE_LIMIT_WINDOW_SECONDS
        ):
            timestamps.popleft()

        if len(timestamps) >= CHAT_RATE_LIMIT_REQUESTS:
            return max(
                1,
                ceil(
                    CHAT_RATE_LIMIT_WINDOW_SECONDS - (now - timestamps[0])
                ),
            )

        timestamps.append(now)
        _rate_limit_requests.move_to_end(client_id)
        while len(_rate_limit_requests) > MAX_RATE_LIMIT_CLIENTS:
            _rate_limit_requests.popitem(last=False)
        return None


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health_check():
    return jsonify(status="ok")


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    return response


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(error="Request body is too large."), 413


@app.post("/api/chat")
def chat():
    retry_after = _rate_limit_retry_after(
        request.remote_addr or "unknown",
        monotonic(),
    )
    if retry_after is not None:
        response = jsonify(
            error=f"Too many requests. Please wait {retry_after} seconds before trying again."
        )
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response

    if not request.is_json:
        return jsonify(error="Content-Type must be application/json."), 415

    try:
        payload = request.get_json()
    except BadRequest:
        return jsonify(error="Request body must be valid JSON."), 400

    if not isinstance(payload, dict):
        return jsonify(error="Request body must be a JSON object."), 400

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return jsonify(error="Messages must be a non-empty list."), 400
    if len(messages) > MAX_HISTORY_MESSAGES or len(messages) % 2 == 0:
        return jsonify(error="Conversation history has an invalid number of messages."), 400

    validated_messages = []
    for index, item in enumerate(messages):
        if not isinstance(item, dict):
            return jsonify(error="Each conversation message must be an object."), 400

        expected_role = "user" if index % 2 == 0 else "assistant"
        role = item.get("role")
        if role != expected_role:
            return jsonify(
                error="Messages must alternate between user and assistant, starting with user."
            ), 400

        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            return jsonify(error="Each conversation message must contain text."), 400

        max_chars = (
            MAX_USER_MESSAGE_CHARS if role == "user" else MAX_ASSISTANT_MESSAGE_CHARS
        )
        if len(content) > max_chars:
            return jsonify(error=f"A conversation message exceeds {max_chars} characters."), 400

        validated_messages.append({"role": role, "content": content.strip()})

    try:
        response_text = generate_response(validated_messages)
    except GeminiServiceError as exc:
        return jsonify(error=str(exc)), 502

    return jsonify(response=response_text)


if __name__ == "__main__":
    app.run(debug=False)
