"""Temporary synthetic-only Azure feasibility probe; no application dependencies."""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FIXTURE = b"Synthetic hosting probe. No patient data.\n"
PAGE = b"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MediFlow hosting check</title>
<style>body{font:18px system-ui;max-width:36em;margin:2em auto;padding:1em}
input,button{font:inherit;padding:.7em;margin:.5em 0;max-width:90%}</style>
<h1>MediFlow hosting check</h1><p>Temporary synthetic test. Enter the locally
prepared test code, turn the development laptop off, then tap Verify.</p>
<label>Test code <input id="token" type="password" autocomplete="off"></label>
<p><button id="verify">Verify hosted API</button></p><pre id="result"></pre>
<script>if(location.hash){document.getElementById('token').value=location.hash.slice(1);history.replaceState(null,'','/');}document.getElementById('verify').onclick=async()=>{
const out=document.getElementById('result');out.textContent='Connecting...';
try{const r=await fetch('/probe',{cache:'no-store',headers:{Authorization:
'Bearer '+document.getElementById('token').value}});const b=await r.json();
out.textContent=r.ok?'Authenticated HTTPS succeeded\\nServer time: '+b.serverTime+
'\\nReceipt: '+b.receipt:'Check failed (HTTP '+r.status+')';}
catch(e){out.textContent='Connection failed. Try again.'}};</script></html>"""


class Storage:
    def __init__(self):
        self.account = os.environ["STORAGE_ACCOUNT"]
        self.spike = os.environ["SPIKE_ID"]
        self.token = ""
        self.expires = 0

    def access_token(self):
        if time.time() + 60 >= self.expires:
            query = urllib.parse.urlencode(
                {
                    "resource": "https://storage.azure.com/",
                    "api-version": "2019-08-01",
                    "client_id": os.environ["IDENTITY_CLIENT_ID"],
                }
            )
            request = urllib.request.Request(
                os.environ["IDENTITY_ENDPOINT"] + "?" + query,
                headers={"X-IDENTITY-HEADER": os.environ["IDENTITY_HEADER"]},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                token = json.load(response)
            self.token = token["access_token"]
            self.expires = int(token["expires_on"])
        return self.token

    def request(self, service, path, method="GET", body=None, headers=None):
        request = urllib.request.Request(
            f"https://{self.account}.{service}.core.windows.net/{path}",
            data=body,
            method=method,
            headers={
                "Authorization": "Bearer " + self.access_token(),
                "x-ms-version": "2023-11-03",
                "x-ms-date": formatdate(usegmt=True),
                **(headers or {}),
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read(65536)

    def blob(self, container):
        return f"{container}/{self.spike}.json"

    def result(self):
        try:
            return json.loads(self.request("blob", self.blob("spike-results")))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def enqueue(self):
        # One fixed object and identifier: this endpoint cannot upload real records.
        self.request(
            "blob",
            self.blob("spike-input"),
            "PUT",
            FIXTURE,
            {
                "x-ms-blob-type": "BlockBlob",
                "Content-Type": "application/octet-stream",
            },
        )
        message = base64.b64encode(json.dumps({"spikeId": self.spike}).encode())
        self.request(
            "queue",
            "spike-jobs/messages?messagettl=600",
            "POST",
            b"<QueueMessage><MessageText>" + message + b"</MessageText></QueueMessage>",
            {"Content-Type": "application/xml"},
        )

    def work(self):
        messages = ET.fromstring(
            self.request("queue", "spike-jobs/messages?numofmessages=1&visibilitytimeout=120")
        )
        for message in messages.findall("QueueMessage"):
            payload = json.loads(base64.b64decode(message.findtext("MessageText")))
            if payload != {"spikeId": self.spike}:
                raise ValueError("Unexpected synthetic fixture identifier")
            data = self.request("blob", self.blob("spike-input"))
            if data != FIXTURE:
                raise ValueError("Unexpected synthetic fixture contents")
            receipt = {
                "state": "completed",
                "sha256": hashlib.sha256(data).hexdigest(),
                "completedAt": datetime.now(UTC).isoformat(),
            }
            try:
                self.request(
                    "blob",
                    self.blob("spike-results"),
                    "PUT",
                    json.dumps(receipt).encode(),
                    {
                        "x-ms-blob-type": "BlockBlob",
                        "Content-Type": "application/json",
                        "If-None-Match": "*",
                    },
                )
            except urllib.error.HTTPError as error:
                if error.code != 412 or self.result().get("sha256") != receipt["sha256"]:
                    raise
            message_id = urllib.parse.quote(message.findtext("MessageId"), safe="")
            pop_receipt = urllib.parse.urlencode({"popreceipt": message.findtext("PopReceipt")})
            self.request("queue", f"spike-jobs/messages/{message_id}?{pop_receipt}", "DELETE")
        return len(messages)


def handler(storage, token, expires):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not log request headers, paths or credentials.

        def reply(self, status, value, content_type="application/json"):
            body = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            provided = self.headers.get("Authorization", "")
            return time.time() < expires and hmac.compare_digest(
                provided.encode(), ("Bearer " + token).encode()
            )

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"status": "ok"})
            if self.path == "/":
                return self.reply(200, PAGE, "text/html; charset=utf-8")
            if not self.authorized():
                return self.reply(401, {"error": "unauthorized"})
            try:
                if self.path == "/probe":
                    return self.reply(
                        200,
                        {
                            "authenticated": True,
                            "serverTime": datetime.now(UTC).isoformat(),
                            "receipt": os.urandom(8).hex(),
                        },
                    )
                if self.path == "/result":
                    result = storage.result()
                    return self.reply(200 if result else 202, result or {"state": "pending"})
                self.reply(404, {"error": "not_found"})
            except (OSError, ValueError, KeyError):
                self.reply(503, {"error": "storage_unavailable"})

        def do_POST(self):
            if not self.authorized():
                return self.reply(401, {"error": "unauthorized"})
            if self.path != "/run":
                return self.reply(404, {"error": "not_found"})
            if self.headers.get("Content-Length", "0") != "0" or self.headers.get(
                "Transfer-Encoding"
            ):
                return self.reply(400, {"error": "synthetic_test_has_no_request_body"})
            try:
                if storage.result():
                    return self.reply(200, {"state": "completed"})
                storage.enqueue()
                self.reply(202, {"state": "queued"})
            except (OSError, ValueError, KeyError):
                self.reply(503, {"error": "storage_unavailable"})

    return Handler


def main():
    storage = Storage()
    if os.environ["SPIKE_MODE"] == "worker":
        # Platform execution timeout is 180 s; no unbounded loops or model calls.
        storage.work()
        print("Synthetic queue execution completed", flush=True)
    else:
        token = os.environ["SPIKE_TOKEN"]
        if len(token) < 32:
            raise ValueError("Missing test credential")
        ThreadingHTTPServer(
            ("0.0.0.0", 8080), handler(storage, token, int(os.environ["SPIKE_EXPIRES"]))
        ).serve_forever()


if __name__ == "__main__":
    main()
