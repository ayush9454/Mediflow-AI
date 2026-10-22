"""Exercise the public probe boundary and duplicate queue delivery behavior."""

import hashlib
import importlib.util
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("runtime.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class HTTPTests(TestCase):
    def setUp(self):
        self.storage = type("FakeStorage", (), {"result": lambda _: None})()
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), probe.handler(self.storage, "a" * 32, time.time() + 60)
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, token=None, body=None):
        request = urllib.request.Request(
            self.url + path,
            data=body,
            headers={"Authorization": token} if token else {},
        )
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.code, json.load(response)

    def test_missing_or_wrong_credentials_never_reach_storage(self):
        self.assertEqual(self.request("/result")[0], 401)
        self.assertEqual(self.request("/run", "Bearer incorrect", b"")[0], 401)
        self.assertEqual(self.request("/health")[0], 200)

    def test_authenticated_https_payload_contains_fresh_receipt(self):
        first = self.request("/probe", "Bearer " + "a" * 32)
        second = self.request("/probe", "Bearer " + "a" * 32)
        self.assertEqual(first[0], 200)
        self.assertTrue(first[1]["authenticated"])
        self.assertNotEqual(first[1]["receipt"], second[1]["receipt"])
        self.assertIn("serverTime", first[1])

    def test_expired_credentials_are_denied(self):
        with patch.object(probe.time, "time", return_value=time.time() + 120):
            self.assertEqual(self.request("/probe", "Bearer " + "a" * 32)[0], 401)

    def test_input_is_fixed_and_cannot_accept_uploaded_records(self):
        self.assertEqual(self.request("/run", "Bearer " + "a" * 32, b"untrusted")[0], 400)


class QueueTests(TestCase):
    def test_duplicate_delivery_preserves_original_completion_and_deletes_after_commit(
        self,
    ):
        message = probe.base64.b64encode(b'{"spikeId":"fixture"}').decode()
        queue = (
            f"<QueueMessagesList><QueueMessage><MessageId>1</MessageId>"
            f"<PopReceipt>a+b</PopReceipt><MessageText>{message}</MessageText>"
            "</QueueMessage></QueueMessagesList>"
        ).encode()
        blobs = {"spike-input/fixture.json": probe.FIXTURE}
        deletes = []

        def request(service, path, method="GET", body=None, headers=None):
            if service == "queue":
                if method == "DELETE":
                    self.assertIn("spike-results/fixture.json", blobs)
                    deletes.append(path)
                    return b""
                return queue
            if method == "GET":
                return blobs[path]
            if path in blobs and headers.get("If-None-Match") == "*":
                raise urllib.error.HTTPError("private", 412, "precondition", {}, None)
            blobs[path] = body
            return b""

        with patch.dict(os.environ, {"STORAGE_ACCOUNT": "synthetic", "SPIKE_ID": "fixture"}):
            storage = probe.Storage()
            storage.request = request
            storage.work()
            original = blobs["spike-results/fixture.json"]
            storage.work()
        self.assertEqual(blobs["spike-results/fixture.json"], original)
        self.assertEqual(json.loads(original)["sha256"], hashlib.sha256(probe.FIXTURE).hexdigest())
        self.assertEqual(len(deletes), 2)
        self.assertIn("popreceipt=a%2Bb", deletes[0])

    def test_invalid_source_never_acknowledges_message(self):
        message = probe.base64.b64encode(b'{"spikeId":"wrong"}').decode()
        queue = (
            f"<QueueMessagesList><QueueMessage><MessageText>{message}</MessageText>"
            "</QueueMessage></QueueMessagesList>"
        ).encode()
        calls = []

        def request(*args):
            calls.append(args)
            return queue

        with patch.dict(os.environ, {"STORAGE_ACCOUNT": "synthetic", "SPIKE_ID": "fixture"}):
            storage = probe.Storage()
            storage.request = request
            with self.assertRaises(ValueError):
                storage.work()
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    main()
