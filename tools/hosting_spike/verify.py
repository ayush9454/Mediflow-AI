"""Record sanitized end-to-end HTTPS/Blob/queue/job evidence for issue 01."""

import hashlib
import json
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import httpx
from cloud import PRIVATE, az, group_path, rest, save, state
from runtime import FIXTURE


def verify():
    s = state()
    token = (PRIVATE / "test-token").read_text()
    authorization = {"Authorization": "Bearer " + token}
    evidence = {
        "checkedAtUtc": datetime.now(UTC).isoformat(),
        "region": s["region"],
        "syntheticOnly": True,
        "laptopOffAndroidTest": "pending",
    }
    with httpx.Client(timeout=40, follow_redirects=False) as client:
        for _ in range(8):
            try:
                response = client.get(s["url"] + "/health")
                if response.status_code == 200:
                    break
            except httpx.RequestError:
                pass
            time.sleep(5)
        else:
            raise RuntimeError("Hosted health probe did not become ready within the bounded wait")
        evidence["healthStatus"] = response.status_code
        evidence["missingCredentialStatus"] = client.get(s["url"] + "/probe").status_code
        evidence["wrongCredentialStatus"] = client.get(
            s["url"] + "/probe", headers={"Authorization": "Bearer invalid"}
        ).status_code
        response = client.get(s["url"] + "/probe", headers=authorization)
        evidence["authenticatedProbeStatus"] = response.status_code
        evidence["authenticatedProbe"] = response.json().get("authenticated") is True
        response = client.post(s["url"] + "/run", headers=authorization)
        evidence["enqueueStatus"] = response.status_code
        if response.status_code not in (200, 202):
            save("hosting-evidence.json", evidence)
            raise RuntimeError(
                "Synthetic enqueue failed; inspect managed identity roles "
                "without exposing credentials"
            )
        public_blob = (
            f"https://{s['storageAccount']}.blob.core.windows.net/spike-input/{s['spikeId']}.json"
        )
        response = client.get(public_blob)
        evidence["anonymousBlobDefaultVersionStatus"] = response.status_code
        evidence["anonymousBlobDefaultVersionError"] = (
            ET.fromstring(response.content).findtext("Code")
            if response.status_code >= 400
            else None
        )
        response = client.get(public_blob, headers={"x-ms-version": "2023-11-03"})
        evidence["anonymousBlobStatus"] = response.status_code
        evidence["anonymousBlobError"] = response.headers.get("x-ms-error-code") or (
            ET.fromstring(response.content).findtext("Code")
            if response.status_code >= 400
            else None
        )
        expected_hash = hashlib.sha256(FIXTURE).hexdigest()
        for _ in range(36):
            response = client.get(s["url"] + "/result", headers=authorization)
            if response.status_code == 200:
                result = response.json()
                evidence["completionState"] = result.get("state")
                evidence["completionHashMatches"] = result.get("sha256") == expected_hash
                evidence["completedAtUtc"] = result.get("completedAt")
                break
            time.sleep(5)
        # Verify persisted receipt through a separate subsequent HTTP request.
        if evidence.get("completionHashMatches"):
            second = client.get(s["url"] + "/result", headers=authorization)
            evidence["durableReceiptStable"] = second.status_code == 200 and second.json() == result
    for _ in range(12):
        executions = az(
            "job-executions",
            "containerapp",
            "job",
            "execution",
            "list",
            "--name",
            s["job"],
            "--resource-group",
            s["resourceGroup"],
        )
        if any(r.get("properties", {}).get("status") == "Succeeded" for r in executions):
            break
        time.sleep(5)
    evidence["hostedExecutionStatuses"] = [
        r.get("properties", {}).get("status") for r in executions
    ]
    app = rest(
        "app-verified",
        group_path(s) + "/providers/Microsoft.App/containerApps/" + s["app"],
    )
    job = rest("job-verified", group_path(s) + "/providers/Microsoft.App/jobs/" + s["job"])
    evidence["apiScale"] = app["properties"]["template"]["scale"]
    evidence["jobTriggerType"] = job["properties"]["configuration"]["triggerType"]
    evidence["jobMaxExecutions"] = job["properties"]["configuration"]["eventTriggerConfig"][
        "scale"
    ]["maxExecutions"]
    evidence["jobRetryLimit"] = job["properties"]["configuration"]["replicaRetryLimit"]
    evidence["jobTimeoutSeconds"] = job["properties"]["configuration"]["replicaTimeout"]
    evidence["passed"] = all(
        (
            evidence["missingCredentialStatus"] == 401,
            evidence["wrongCredentialStatus"] == 401,
            evidence["authenticatedProbeStatus"] == 200,
            evidence["authenticatedProbe"],
            evidence["anonymousBlobStatus"] == 401,
            evidence["anonymousBlobError"] == "NoAuthenticationInformation",
            evidence.get("completionState") == "completed",
            evidence.get("completionHashMatches"),
            evidence.get("durableReceiptStable"),
            evidence["jobTriggerType"] == "Event",
            evidence["jobMaxExecutions"] == 1,
            "Succeeded" in evidence["hostedExecutionStatuses"],
        )
    )
    save("hosting-evidence.json", evidence)
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        verify()
    except (RuntimeError, httpx.RequestError) as error:
        print(
            str(error)
            if isinstance(error, RuntimeError)
            else "HTTP probe failed; no credentials or raw errors emitted"
        )
        raise SystemExit(1) from None
