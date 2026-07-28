"""
Orchestrator Lambda.

Flow:
  1. Parse the incoming chat message + session id from API Gateway.
  2. Load recent conversation history from DynamoDB.
  3. Build a prompt (system rules + history + new message) and call Bedrock.
  4. Invoke the Validator function to check/format the response.
  5. Save the turn back to DynamoDB and return the reply to the caller.
"""

import json
import os
import time
import uuid
import logging

import boto3
from business_context import SYSTEM_PROMPT, MAX_HISTORY_TURNS

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")
lambda_client = boto3.client("lambda")

TABLE_NAME = os.environ["CONVERSATION_TABLE"]
MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
VALIDATOR_FUNCTION_NAME = os.environ["VALIDATOR_FUNCTION_NAME"]
HISTORY_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

table = dynamodb.Table(TABLE_NAME)


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Request body must be valid JSON."})

    message = (body.get("message") or "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not message:
        return _response(400, {"error": "Field 'message' is required."})

    history = _load_history(session_id)

    try:
        reply_text = _call_bedrock(message, history)
    except Exception:
        logger.exception("Bedrock call failed for session %s", session_id)
        return _response(502, {
            "session_id": session_id,
            "reply": "Something went wrong on our end. Please try again in a moment.",
            "escalate": True,
        })

    validated = _invoke_validator(message, reply_text)

    _save_turn(session_id, message, validated["reply"])

    return _response(200, {
        "session_id": session_id,
        "reply": validated["reply"],
        "escalate": validated["escalate"],
    })


def _load_history(session_id: str):
    item = table.get_item(Key={"session_id": session_id}).get("Item")
    if not item:
        return []
    return item.get("turns", [])[-MAX_HISTORY_TURNS:]


def _call_bedrock(message: str, history: list) -> str:
    messages = []
    for turn in history:
        messages.append({"role": "user", "content": [{"text": turn["user"]}]})
        messages.append({"role": "assistant", "content": [{"text": turn["assistant"]}]})
    messages.append({"role": "user", "content": [{"text": message}]})

    response = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=messages,
        inferenceConfig={"maxTokens": 400, "temperature": 0.3},
    )
    return response["output"]["message"]["content"][0]["text"]


def _invoke_validator(message: str, draft_reply: str) -> dict:
    payload = {"message": message, "draft_reply": draft_reply}
    response = lambda_client.invoke(
        FunctionName=VALIDATOR_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode(),
    )
    result = json.loads(response["Payload"].read())
    return {
        "reply": result.get("reply", draft_reply),
        "escalate": result.get("escalate", False),
    }


def _save_turn(session_id: str, user_message: str, assistant_reply: str):
    item = table.get_item(Key={"session_id": session_id}).get("Item") or {
        "session_id": session_id,
        "turns": [],
    }
    turns = item.get("turns", [])
    turns.append({"user": user_message, "assistant": assistant_reply})
    turns = turns[-MAX_HISTORY_TURNS:]

    table.put_item(Item={
        "session_id": session_id,
        "turns": turns,
        "ttl": int(time.time()) + HISTORY_TTL_SECONDS,
    })


def _response(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
