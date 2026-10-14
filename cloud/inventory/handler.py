"""Cleansheet sponsor-inventory API (Lambda function URL, DynamoDB table in $TABLE).

  GET /viewers/<viewer>/prefs        the viewer's hidden categories and treatment per category
                                     (defaults until they save any)
  PUT /viewers/<viewer>/prefs        save them: {"hidden": [...], "treatments": {category: mode}}
  GET /videos/<video>/inventory      {"slots": {board id: replacement sponsor}} for that video

Table items: pk viewer#<id> / sk prefs, and pk video#<id> / sk board#<track id> (seeded by
cloud/seed_inventory.py from the sidecar tracks). Viewer ids are opaque client-chosen strings;
there is no sign-in, so prefs are not private.
"""

from __future__ import annotations

import base64
import json
import os
import re

import boto3

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE"])
HIDEABLE = ("gambling", "alcohol")
MODES = ("auto", "replace", "blur")
DEFAULT_PREFS = {"hidden": list(HIDEABLE), "treatments": {}}
ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def respond(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def get_prefs(viewer: str) -> dict:
    item = TABLE.get_item(Key={"pk": f"viewer#{viewer}", "sk": "prefs"}).get("Item")
    if not item:
        return respond(200, {**DEFAULT_PREFS, "saved": False})
    return respond(200, {"hidden": item["hidden"], "treatments": item["treatments"], "saved": True})


def put_prefs(viewer: str, raw: str | None) -> dict:
    try:
        body = json.loads(raw or "")
        hidden, treatments = body["hidden"], body.get("treatments", {})
    except (ValueError, KeyError, TypeError):
        return respond(400, {"error": 'expected {"hidden": [...], "treatments": {...}}'})
    if not isinstance(hidden, list) or any(c not in HIDEABLE for c in hidden) or len(set(hidden)) != len(hidden):
        return respond(400, {"error": f"hidden must be a list of distinct categories from {HIDEABLE}"})
    if not isinstance(treatments, dict) or any(c not in HIDEABLE or m not in MODES for c, m in treatments.items()):
        return respond(400, {"error": f"treatments maps {HIDEABLE} to one of {MODES}"})
    TABLE.put_item(Item={"pk": f"viewer#{viewer}", "sk": "prefs", "hidden": hidden, "treatments": treatments})
    return respond(200, {"hidden": hidden, "treatments": treatments, "saved": True})


def get_inventory(video: str) -> dict:
    slots, kwargs = {}, {}
    while True:
        page = TABLE.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :sk)",
            ExpressionAttributeValues={":pk": f"video#{video}", ":sk": "board#"},
            **kwargs,
        )
        slots.update({i["sk"].removeprefix("board#"): i["sponsor"] for i in page["Items"]})
        if "LastEvaluatedKey" not in page:
            return respond(200, {"video": video, "slots": slots})
        kwargs = {"ExclusiveStartKey": page["LastEvaluatedKey"]}


def handler(event: dict, _context) -> dict:
    method = event["requestContext"]["http"]["method"]
    parts = [p for p in event.get("rawPath", "").split("/") if p]
    if len(parts) == 3 and parts[0] == "viewers" and parts[2] == "prefs" and ID.match(parts[1]):
        if method == "GET":
            return get_prefs(parts[1])
        if method == "PUT":
            body = event.get("body")
            if body and event.get("isBase64Encoded"):
                body = base64.b64decode(body).decode()
            return put_prefs(parts[1], body)
        return respond(405, {"error": "GET or PUT"})
    if len(parts) == 3 and parts[0] == "videos" and parts[2] == "inventory" and ID.match(parts[1]):
        if method == "GET":
            return get_inventory(parts[1])
        return respond(405, {"error": "GET"})
    return respond(404, {"error": "routes: /viewers/<id>/prefs, /videos/<id>/inventory"})
