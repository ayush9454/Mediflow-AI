"""Temporary real Azure Blob adapter check. All account/credential state stays ignored."""

import argparse
import base64
import json
import secrets
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from azure.core.credentials import AccessToken
from azure_probe import AzureProbe
from reportlab.pdfgen import canvas

from mediflow.errors import ApplicationError
from mediflow.uploads.platform import BlobDocuments

TAGS = {"project": "mediflow", "purpose": "issue-05-upload-smoke", "temporary": "true"}


class UploadProbe(AzureProbe):
    def __init__(self, root: Path):
        super().__init__(root, ".tooling/issue-5/azure", TAGS)

    def init(self) -> None:
        if (self.private / "state.json").exists():
            raise RuntimeError("State exists; resume or clean this probe first")
        self.check_subscription()
        suffix = secrets.token_hex(4)
        state = {
            "group": "mediflow-upload-" + suffix,
            "storage": "mfupload" + suffix,
            "region": "centralindia",
            "probeId": uuid.uuid4().hex,
        }
        self.save("state.json", state)
        self.az(
            "group-create",
            "group",
            "create",
            "--name",
            state["group"],
            "--location",
            state["region"],
            "--tags",
            *(k + "=" + v for k, v in TAGS.items()),
        )
        print("Temporary upload group created; spending protection On", flush=True)

    def infrastructure(self) -> None:
        state = self.state()
        self.guard(state)
        storage = (
            self.group(state) + "/providers/Microsoft.Storage/storageAccounts/" + state["storage"]
        )
        account = self.rest(
            "storage-create",
            storage,
            "PUT",
            {
                "location": state["region"],
                "kind": "StorageV2",
                "sku": {"name": "Standard_LRS"},
                "tags": TAGS,
                "properties": {
                    "accessTier": "Hot",
                    "allowBlobPublicAccess": False,
                    "allowSharedKeyAccess": False,
                    "supportsHttpsTrafficOnly": True,
                    "minimumTlsVersion": "TLS1_2",
                },
            },
            version="2023-05-01",
        )
        if account is None:
            account = self.rest("storage-status", storage, version="2023-05-01")
        if account.get("properties", {}).get("provisioningState") != "Succeeded":
            print(
                "Storage provisioning; repeat infrastructure after it succeeds",
                flush=True,
            )
            return
        self.rest(
            "container-create",
            storage + "/blobServices/default/containers/reports",
            "PUT",
            {"properties": {"publicAccess": "None"}},
            version="2023-05-01",
        )
        token = self.az(
            "owner-token",
            "account",
            "get-access-token",
            "--resource",
            "https://management.azure.com/",
        )
        payload = token["accessToken"].split(".")[1]
        principal = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["oid"]
        self.role(
            "owner-blob-contributor",
            storage,
            principal,
            "ba92f5b4-2d11-453d-a403-e96b0029c9fe",
            "User",
        )
        print(
            "Private storage provisioned; shared-key and anonymous access disabled",
            flush=True,
        )

    def check(self) -> None:
        state = self.state()
        self.guard(state)
        probe = self

        class Credential:
            def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
                data = probe.az(
                    "storage-token",
                    "account",
                    "get-access-token",
                    "--resource",
                    "https://storage.azure.com/",
                )
                return AccessToken(data["accessToken"], int(data["expires_on"]))

        endpoint = "https://" + state["storage"] + ".blob.core.windows.net"
        documents = BlobDocuments(endpoint, "reports", Credential())
        source = BytesIO()
        pdf = canvas.Canvas(source, invariant=True)
        pdf.drawString(40, 750, "Synthetic laboratory report Result Reference interval")
        pdf.drawString(40, 720, "Glucose 92 mg/dL Reference range 70-100")
        pdf.save()
        content = source.getvalue()
        key = "smoke/" + state["probeId"] + ".pdf"
        try:
            documents.delete(key)
            documents.put(key, BytesIO(content), len(content))
            assert documents.read(key) == content, "Private bytes changed"
            assert key in documents.keys("smoke/"), "Private prefix listing missed the object"
            response = httpx.get(
                endpoint + "/reports/" + key,
                headers={"x-ms-version": "2023-11-03"},
                timeout=20,
            )
            assert response.status_code in {401, 403, 409}, "Anonymous read was not denied"
            try:
                documents.put(key, BytesIO(b"replacement"), len(b"replacement"))
            except ApplicationError:
                pass
            else:
                raise RuntimeError("Immutable Blob overwrite was accepted")
            assert documents.read(key) == content, "Original was overwritten"
            documents.delete(key)
            exists = documents.container.get_blob_client(key).exists(timeout=10)
            assert not exists, "Temporary blob remains"
            assert key not in documents.keys("smoke/"), "Deleted object remains in prefix listing"
            report = {
                "privateUploadDownload": True,
                "boundedPrefixListing": True,
                "anonymousStatus": response.status_code,
                "overwriteDenied": True,
                "originalPreserved": True,
                "temporaryBlobDeleted": True,
                "spendingProtection": "On",
                "scope": "real Azure Blob adapter; no hosted API deployment",
                "observedAtEpoch": int(time.time()),
            }
            destination = self.root / "evaluation/reports/private-upload-cloud.json"
            destination.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report), flush=True)
        finally:
            documents.delete(key)

    def cleanup(self) -> None:
        state = self.state()
        self.check_group(state)
        self.az(
            "group-delete",
            "group",
            "delete",
            "--name",
            state["group"],
            "--yes",
            "--no-wait",
        )
        print("Temporary group deletion requested", flush=True)

    def cleanup_status(self) -> None:
        state = self.state()
        exists = self.az("group-exists", "group", "exists", "--name", state["group"])
        print("all temporary resources deleted:", exists is False, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["init", "infrastructure", "check", "cleanup", "cleanup-status"],
    )
    args = parser.parse_args()
    probe = UploadProbe(Path(__file__).resolve().parents[1])
    getattr(probe, args.stage.replace("-", "_"))()


if __name__ == "__main__":
    main()
