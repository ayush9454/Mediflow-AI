"""Deploy/check/delete the isolated issue-01 probe. All cloud state stays ignored.

Run with backend/.venv/bin/python tools/hosting_spike/cloud.py <stage>.
Requires the owner-authorized .tooling/issue-1/az login wrapper.
"""

import argparse
import base64
import json
import os
import secrets
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / ".tooling/issue-1"
AZ = str(PRIVATE / "az")
API = "2026-07-01"
TAGS = {"project": "mediflow", "purpose": "issue-01-spike", "temporary": "true"}


def save(name, value):
    fd = os.open(PRIVATE / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2))


def az(name, *args, timeout=240):
    result = subprocess.run(
        [
            AZ,
            *args,
            "--subscription",
            settings()["AZURE_SUBSCRIPTION_ID"],
            "--only-show-errors",
            "--output",
            "json",
        ],
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    save(name + ".json", result.stdout if result.returncode == 0 else result.stderr)
    if result.returncode:
        raise RuntimeError(f"{name} failed; details retained in ignored private state")
    return json.loads(result.stdout) if result.stdout.strip() else None


def rest(name, path, method="GET", body=None, version=API):
    args = [
        "rest",
        "--method",
        method,
        "--url",
        "https://management.azure.com" + path + "?api-version=" + version,
    ]
    if body is not None:
        save(name + "-request.json", body)
        args += ["--body", "@" + str(PRIVATE / (name + "-request.json"))]
    return az(name, *args)


def wait_resource(name, path, version=API):
    for _ in range(120):
        try:
            result = rest(name, path, version=version)
        except RuntimeError:
            error = (PRIVATE / (name + ".json")).read_text()
            if not any(code in error for code in ("InternalServerError", "TooManyRequests")):
                raise
            time.sleep(5)
            continue
        status = result.get("properties", {}).get("provisioningState")
        if status == "Succeeded":
            return result
        if status in ("Failed", "Canceled"):
            raise RuntimeError(f"{name} provisioning {status}; inspect private logs")
        time.sleep(5)
    raise RuntimeError(f"{name} provisioning is pending; inspect private logs before continuing")


def settings():
    values = {}
    for line in (PRIVATE / ".env").read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key] = (
                value[1:-1].replace("'\\''", "'")
                if value.startswith("'") and value.endswith("'")
                else value
            )
    return values


def state():
    return json.loads((PRIVATE / "cloud-state.json").read_text())


def scope():
    return "/subscriptions/" + settings()["AZURE_SUBSCRIPTION_ID"]


def group_path(s):
    return scope() + "/resourceGroups/" + s["resourceGroup"]


def guard(s):
    account = rest("subscription-current", scope(), version="2022-12-01")
    if (
        account.get("state") != "Enabled"
        or account.get("subscriptionPolicies", {}).get("spendingLimit", "").lower() != "on"
    ):
        raise RuntimeError("Enabled subscription with spending protection On is required")
    group = az("group-current", "group", "show", "--name", s["resourceGroup"])
    if any(group.get("tags", {}).get(k) != v for k, v in TAGS.items()):
        raise RuntimeError("Resource group is not tagged as this temporary probe")


def init():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    os.chmod(PRIVATE, 0o700)
    if (PRIVATE / "cloud-state.json").exists():
        raise RuntimeError(
            "State already exists; resume its stages instead of creating another group"
        )
    account = rest("subscription-current", scope(), version="2022-12-01")
    if (
        account.get("state") != "Enabled"
        or account.get("subscriptionPolicies", {}).get("spendingLimit", "").lower() != "on"
    ):
        raise RuntimeError("Enabled subscription with spending protection On is required")
    suffix = secrets.token_hex(3)
    s = {
        "region": "centralindia",
        "resourceGroup": "mediflow-spike-" + suffix,
        "environment": "mf-spike-env",
        "storageAccount": "mfspike" + suffix,
        "identity": "mf-spike-identity",
        "app": "mf-spike-api",
        "job": "mf-spike-worker",
        "queue": "spike-jobs",
        "inputContainer": "spike-input",
        "resultContainer": "spike-results",
        "spikeId": uuid.uuid4().hex,
    }
    save("cloud-state.json", s)
    az(
        "group-create",
        "group",
        "create",
        "--name",
        s["resourceGroup"],
        "--location",
        s["region"],
        "--tags",
        *(k + "=" + v for k, v in TAGS.items()),
    )
    az(
        "app-provider-register",
        "provider",
        "register",
        "--namespace",
        "Microsoft.App",
        "--wait",
        timeout=600,
    )
    environment(s)


def environment(s):
    path = group_path(s) + "/providers/Microsoft.App/managedEnvironments/" + s["environment"]
    rest(
        "environment-create",
        path,
        "PUT",
        {
            "location": s["region"],
            "tags": TAGS,
            "properties": {
                "environmentMode": "WorkloadProfiles",
                "workloadProfiles": [{"name": "Consumption", "workloadProfileType": "Consumption"}],
                "appLogsConfiguration": {"destination": None},
            },
        },
        "2026-07-01",
    )
    result = wait_resource("environment-ready", path, "2026-07-01")
    if result["properties"].get("environmentMode") != "WorkloadProfiles":
        raise RuntimeError("Jobs require a standard WorkloadProfiles environment")
    print(
        "Standard environment ready with only the Consumption workload profile",
        flush=True,
    )


def infrastructure(s):
    guard(s)
    usage = az(
        "environment-quotas",
        "containerapp",
        "env",
        "list-usages",
        "--name",
        s["environment"],
        "--resource-group",
        s["resourceGroup"],
    )
    rows = usage.get("value", []) if isinstance(usage, dict) else usage
    consumption = [
        row
        for row in rows
        if row.get("name", {}).get("value") == "ManagedEnvironmentConsumptionCores"
    ]
    if not consumption or consumption[0]["limit"] - consumption[0]["currentValue"] < 0.5:
        raise RuntimeError(
            "At least 0.5 available Consumption cores must be verified before continuing"
        )
    for row in rows:
        print(
            "Environment quota:",
            row.get("name", {}).get("value"),
            row.get("currentValue"),
            "/",
            row.get("limit"),
            flush=True,
        )
    for provider in ("Microsoft.Storage", "Microsoft.ManagedIdentity"):
        az(
            provider.replace(".", "-") + "-register",
            "provider",
            "register",
            "--namespace",
            provider,
            "--wait",
            timeout=600,
        )
    storage_path = (
        group_path(s) + "/providers/Microsoft.Storage/storageAccounts/" + s["storageAccount"]
    )
    rest(
        "storage-create",
        storage_path,
        "PUT",
        {
            "location": s["region"],
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
        "2023-05-01",
    )
    wait_resource("storage-ready", storage_path, "2023-05-01")
    for container in (s["inputContainer"], s["resultContainer"]):
        rest(
            "container-" + container,
            storage_path + "/blobServices/default/containers/" + container,
            "PUT",
            {"properties": {"publicAccess": "None"}},
            "2023-05-01",
        )
    rest(
        "queue-create",
        storage_path + "/queueServices/default/queues/" + s["queue"],
        "PUT",
        {"properties": {}},
        "2023-05-01",
    )
    identity_path = (
        group_path(s)
        + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/"
        + s["identity"]
    )
    identity = rest(
        "identity-create",
        identity_path,
        "PUT",
        {"location": s["region"], "tags": TAGS},
        "2023-01-31",
    )
    s["identityId"] = identity["id"]
    s["identityClientId"] = identity["properties"]["clientId"]
    save("cloud-state.json", s)
    roles = {
        "blob": "ba92f5b4-2d11-453d-a403-e96b0029c9fe",
        "queue": "974c5e8b-45b9-4653-ba55-5f855dd0fb88",
    }
    for kind, role in roles.items():
        assignment = str(uuid.uuid5(uuid.NAMESPACE_URL, storage_path + identity_path + role))
        rest(
            "role-" + kind,
            storage_path + "/providers/Microsoft.Authorization/roleAssignments/" + assignment,
            "PUT",
            {
                "properties": {
                    "principalId": identity["properties"]["principalId"],
                    "principalType": "ServicePrincipal",
                    "roleDefinitionId": scope()
                    + "/providers/Microsoft.Authorization/roleDefinitions/"
                    + role,
                }
            },
            "2022-04-01",
        )
    print(
        "Private containers, queue and storage-scoped managed-identity roles ready",
        flush=True,
    )


def deploy(s):
    guard(s)
    if "image" not in s:
        # Resolve the official multi-platform image to an immutable digest, without Docker.
        import urllib.request

        token_url = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull"
        with urllib.request.urlopen(token_url, timeout=30) as response:
            token = json.load(response)["token"]
        request = urllib.request.Request(
            "https://registry-1.docker.io/v2/library/python/manifests/3.12-slim",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": (
                    "application/vnd.oci.image.index.v1+json, "
                    "application/vnd.docker.distribution.manifest.list.v2+json"
                ),
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            s["image"] = "docker.io/library/python@" + response.headers["Docker-Content-Digest"]
        save("cloud-state.json", s)
    if not (PRIVATE / "test-token").exists():
        save("test-token", secrets.token_hex(16))
        s["expires"] = int(time.time()) + 86400
        save("cloud-state.json", s)
    code = base64.b64encode((Path(__file__).parent / "runtime.py").read_bytes()).decode()
    env = [
        {"name": k, "value": str(v)}
        for k, v in {
            "STORAGE_ACCOUNT": s["storageAccount"],
            "SPIKE_ID": s["spikeId"],
            "IDENTITY_CLIENT_ID": s["identityClientId"],
            "SPIKE_CODE": code,
            "SPIKE_EXPIRES": s["expires"],
        }.items()
    ]
    container = {
        "name": "probe",
        "image": s["image"],
        "command": [
            "python",
            "-c",
            "import os,base64;exec(base64.b64decode(os.environ['SPIKE_CODE']))",
        ],
        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
    }
    common = {
        "location": s["region"],
        "tags": TAGS,
        "identity": {
            "type": "UserAssigned",
            "userAssignedIdentities": {s["identityId"]: {}},
        },
    }
    environment_id = (
        group_path(s) + "/providers/Microsoft.App/managedEnvironments/" + s["environment"]
    )
    job = {
        **common,
        "properties": {
            "environmentId": environment_id,
            "workloadProfileName": "Consumption",
            "configuration": {
                "triggerType": "Event",
                "replicaTimeout": 180,
                "replicaRetryLimit": 0,
                "eventTriggerConfig": {
                    "replicaCompletionCount": 1,
                    "parallelism": 1,
                    "scale": {
                        "minExecutions": 0,
                        "maxExecutions": 1,
                        "pollingInterval": 30,
                        "rules": [
                            {
                                "name": "synthetic-queue",
                                "type": "azure-queue",
                                "identity": s["identityId"],
                                "metadata": {
                                    "accountName": s["storageAccount"],
                                    "queueName": s["queue"],
                                    "queueLength": "1",
                                    "activationQueueLength": "0",
                                },
                            }
                        ],
                    },
                },
            },
            "template": {
                "containers": [
                    {
                        **container,
                        "env": env + [{"name": "SPIKE_MODE", "value": "worker"}],
                    }
                ]
            },
        },
    }
    rest(
        "job-create",
        group_path(s) + "/providers/Microsoft.App/jobs/" + s["job"],
        "PUT",
        job,
    )
    app = {
        **common,
        "properties": {
            "environmentId": environment_id,
            "workloadProfileName": "Consumption",
            "configuration": {
                "activeRevisionsMode": "Single",
                "ingress": {
                    "external": True,
                    "targetPort": 8080,
                    "allowInsecure": False,
                    "transport": "auto",
                },
                "secrets": [
                    {
                        "name": "probe-token",
                        "value": (PRIVATE / "test-token").read_text(),
                    }
                ],
            },
            "template": {
                "scale": {
                    "minReplicas": 0,
                    "maxReplicas": 1,
                    "rules": [
                        {
                            "name": "http",
                            "http": {"metadata": {"concurrentRequests": "1"}},
                        }
                    ],
                },
                "containers": [
                    {
                        **container,
                        "env": env
                        + [
                            {"name": "SPIKE_MODE", "value": "api"},
                            {"name": "SPIKE_TOKEN", "secretRef": "probe-token"},
                        ],
                        "probes": [
                            {
                                "type": "Readiness",
                                "httpGet": {"path": "/health", "port": 8080},
                                "initialDelaySeconds": 3,
                                "periodSeconds": 5,
                            }
                        ],
                    }
                ],
            },
        },
    }
    rest(
        "app-create",
        group_path(s) + "/providers/Microsoft.App/containerApps/" + s["app"],
        "PUT",
        app,
    )
    result = wait_resource(
        "app-ready",
        group_path(s) + "/providers/Microsoft.App/containerApps/" + s["app"],
    )
    s["url"] = "https://" + result["properties"]["configuration"]["ingress"]["fqdn"]
    save("cloud-state.json", s)
    print(
        "Bounded API and event-driven job submitted; endpoint saved privately",
        flush=True,
    )


def cleanup(s):
    # Cleanup remains possible even if credit has expired or protection changed.
    group = az("cleanup-group-check", "group", "show", "--name", s["resourceGroup"])
    if any(group.get("tags", {}).get(k) != v for k, v in TAGS.items()):
        raise RuntimeError("Refusing to delete a group without the probe ownership tags")
    az(
        "cleanup-delete",
        "group",
        "delete",
        "--name",
        s["resourceGroup"],
        "--yes",
        "--no-wait",
    )
    print(
        "Temporary resource-group deletion requested; "
        "verify group absence before recording completion"
    )


def cleanup_status(s):
    exists = az("cleanup-exists", "group", "exists", "--name", s["resourceGroup"])
    save(
        "cleanup-evidence.json",
        {
            "resourceGroupExists": exists,
            "temporaryResourcesDeleted": not exists,
        },
    )
    print("Temporary resource group absent:", not exists)
    return not exists


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["init", "environment", "infrastructure", "deploy", "cleanup", "cleanup-status"],
    )
    stage = parser.parse_args().stage
    try:
        if stage == "init":
            init()
        elif stage == "environment":
            s = state()
            guard(s)
            environment(s)
        elif stage == "cleanup-status":
            if not cleanup_status(state()):
                raise SystemExit(2)
        else:
            {"infrastructure": infrastructure, "deploy": deploy, "cleanup": cleanup}[stage](state())
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(
            str(error)
            if isinstance(error, RuntimeError)
            else "Cloud command deadline exceeded; check private logs"
        )
        raise SystemExit(1) from None
