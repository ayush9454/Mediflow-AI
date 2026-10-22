"""Staged, tagged temporary Azure OCR acceptance probe. Private state stays ignored.

Use --workspace when running from an isolated worktree against integrated source.
Stages: init, infrastructure, build-push, deploy, start, status, collect, cleanup,
cleanup-status. No stage converts subscriptions, enables registry admins, or creates
Log Analytics/private networking. Always finish cleanup and verify group absence.
"""

import argparse
import base64
import json
import os
import secrets
import shlex
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TAGS = {"project": "mediflow", "purpose": "issue-07-ocr-smoke", "temporary": "true"}
API = "2026-07-01"


class Probe:
    def __init__(self, root: Path, docker_binary: str, docker_host: str | None):
        self.root = root.resolve()
        self.private = self.root / ".tooling/issue-7/azure"
        self.private.mkdir(parents=True, exist_ok=True)
        self.private.chmod(0o700)
        self.az_path = str(self.root / ".tooling/issue-1/az")
        subscription = None
        for line in (self.root / ".tooling/issue-1/.env").read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.removeprefix("export ").strip() == "AZURE_SUBSCRIPTION_ID":
                values = shlex.split(value, comments=True)
                if len(values) != 1:
                    raise RuntimeError("AZURE_SUBSCRIPTION_ID must be one shell-quoted value")
                subscription = values[0]
        if not subscription:
            raise RuntimeError("Missing AZURE_SUBSCRIPTION_ID in private hosting settings")
        self.subscription = subscription
        self.scope = "/subscriptions/" + self.subscription
        self.docker = [docker_binary]
        if docker_host:
            self.docker += ["--host", docker_host]
        docker_config = self.root / ".tooling/issue-7/docker-config"
        docker_config.mkdir(parents=True, exist_ok=True)
        docker_config.chmod(0o700)
        self.environment = dict(os.environ, DOCKER_CONFIG=str(docker_config))

    def save(self, name: str, value: Any) -> None:
        fd = os.open(self.private / name, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(value if isinstance(value, str) else json.dumps(value, indent=2))

    def state(self) -> dict[str, Any]:
        return json.loads((self.private / "state.json").read_text())

    def az(self, label: str, *args: str, timeout: int = 240) -> Any:
        result = subprocess.run(
            [
                self.az_path,
                *args,
                "--subscription",
                self.subscription,
                "--only-show-errors",
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        self.save(label + ".json", result.stdout if result.returncode == 0 else result.stderr)
        if result.returncode:
            raise RuntimeError(label + " failed; inspect private response")
        return json.loads(result.stdout) if result.stdout.strip() else None

    def rest(
        self,
        label: str,
        path: str,
        method: str = "GET",
        body: Any = None,
        version: str = API,
    ) -> Any:
        args = [
            "rest",
            "--method",
            method,
            "--url",
            "https://management.azure.com" + path + "?api-version=" + version,
        ]
        if body is not None:
            self.save(label + "-request.json", body)
            args += ["--body", "@" + str(self.private / (label + "-request.json"))]
        return self.az(label, *args)

    def group(self, state: dict[str, Any]) -> str:
        return self.scope + "/resourceGroups/" + state["group"]

    def check_subscription(self) -> None:
        account = self.rest("subscription-check", self.scope, version="2022-12-01")
        if (
            account.get("state") != "Enabled"
            or account.get("subscriptionPolicies", {}).get("spendingLimit", "").lower() != "on"
        ):
            raise RuntimeError("Enabled student subscription with spending protection On required")

    def guard(self, state: dict[str, Any]) -> None:
        self.check_subscription()
        self.check_group(state)

    def check_group(self, state: dict[str, Any]) -> None:
        group = self.az("ownership-check", "group", "show", "--name", state["group"])
        if any(group.get("tags", {}).get(key) != value for key, value in TAGS.items()):
            raise RuntimeError("Temporary group ownership tags do not match")

    def init(self) -> None:
        if (self.private / "state.json").exists():
            raise RuntimeError("State exists: resume or clean it; do not create another group")
        self.check_subscription()
        suffix = secrets.token_hex(3)
        state = {
            "group": "mediflow-ocr-" + suffix,
            "registry": "mfocr" + suffix,
            "storage": "mfocrresults" + suffix,
            "identity": "ocr-probe-identity",
            "environment": "ocr-consumption",
            "job": "ocr-probe",
            "region": "centralindia",
            "spike_id": uuid.uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
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
        print(
            "Fresh tagged OCR probe group created; spending protection verified On",
            flush=True,
        )

    def infrastructure(self) -> None:
        state = self.state()
        self.guard(state)
        group = self.group(state)
        environment = group + "/providers/Microsoft.App/managedEnvironments/" + state["environment"]
        self.rest(
            "environment-create",
            environment,
            "PUT",
            {
                "location": state["region"],
                "tags": TAGS,
                "properties": {
                    "environmentMode": "WorkloadProfiles",
                    "workloadProfiles": [
                        {"name": "Consumption", "workloadProfileType": "Consumption"}
                    ],
                    "appLogsConfiguration": {"destination": None},
                },
            },
        )
        registry = self.az(
            "registry-create",
            "acr",
            "create",
            "--name",
            state["registry"],
            "--resource-group",
            state["group"],
            "--location",
            state["region"],
            "--sku",
            "Basic",
            "--admin-enabled",
            "false",
            "--role-assignment-mode",
            "rbac",
            "--tags",
            *(k + "=" + v for k, v in TAGS.items()),
            timeout=600,
        )
        if registry.get("adminUserEnabled") or registry.get("sku", {}).get("name") != "Basic":
            raise RuntimeError("Expected Basic ACR with admin access disabled")
        state["registry_id"] = registry["id"]
        state["registry_server"] = registry["loginServer"]
        identity_path = (
            group
            + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/"
            + state["identity"]
        )
        identity = self.rest(
            "identity-create",
            identity_path,
            "PUT",
            {"location": state["region"], "tags": TAGS},
            version="2023-01-31",
        )
        state["identity_id"] = identity["id"]
        state["identity_client_id"] = identity["properties"]["clientId"]
        state["identity_principal_id"] = identity["properties"]["principalId"]
        storage_path = group + "/providers/Microsoft.Storage/storageAccounts/" + state["storage"]
        self.rest(
            "storage-create",
            storage_path,
            "PUT",
            {
                "location": state["region"],
                "kind": "StorageV2",
                "sku": {"name": "Standard_LRS"},
                "tags": TAGS,
                "properties": {
                    "allowBlobPublicAccess": False,
                    "allowSharedKeyAccess": False,
                    "supportsHttpsTrafficOnly": True,
                    "minimumTlsVersion": "TLS1_2",
                },
            },
            version="2023-05-01",
        )
        self.rest(
            "container-create",
            storage_path + "/blobServices/default/containers/ocr-results",
            "PUT",
            {"properties": {"publicAccess": "None"}},
            version="2023-05-01",
        )
        self.role(
            "registry-pull",
            registry["id"],
            state["identity_principal_id"],
            "7f951dda-4ed3-4680-a7ca-43fe172d538d",
            "ServicePrincipal",
        )
        self.role(
            "result-write",
            storage_path,
            state["identity_principal_id"],
            "ba92f5b4-2d11-453d-a403-e96b0029c9fe",
            "ServicePrincipal",
        )
        token = self.az(
            "owner-arm-token",
            "account",
            "get-access-token",
            "--resource",
            "https://management.azure.com/",
        )
        payload = token["accessToken"].split(".")[1]
        principal = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["oid"]
        self.role(
            "result-read",
            storage_path,
            principal,
            "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",
            "User",
        )
        self.save("state.json", state)
        print(
            "Consumption environment, private Basic registry, result Blob "
            "and scoped identities submitted",
            flush=True,
        )

    def role(self, label: str, scope: str, principal: str, role: str, kind: str) -> None:
        assignment = str(uuid.uuid5(uuid.NAMESPACE_URL, scope + principal + role))
        self.rest(
            label,
            scope + "/providers/Microsoft.Authorization/roleAssignments/" + assignment,
            "PUT",
            {
                "properties": {
                    "principalId": principal,
                    "principalType": kind,
                    "roleDefinitionId": self.scope
                    + "/providers/Microsoft.Authorization/roleDefinitions/"
                    + role,
                }
            },
            version="2022-04-01",
        )

    def docker_run(
        self, label: str, *args: str, stdin: str | None = None, timeout: int = 600
    ) -> str:
        result = subprocess.run(
            [*self.docker, *args],
            env=self.environment,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        self.save(label + ".log", result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(label + " failed; inspect private log")
        return result.stdout

    def build_push(self) -> None:
        state = self.state()
        self.guard(state)
        context = self.private / "build"
        context.mkdir(exist_ok=True)
        for name in ("pyproject.toml", "uv.lock", "Dockerfile.worker"):
            shutil.copy2(self.root / "backend" / name, context / name)
        shutil.copytree(self.root / "backend/src", context / "src", dirs_exist_ok=True)
        smoke = context / "smoke"
        smoke.mkdir(exist_ok=True)
        shutil.copy2(Path(__file__).with_name("runtime.py"), smoke / "runtime.py")
        shutil.copy2(self.root / "tools/hosting_spike/runtime.py", smoke / "hosting_runtime.py")
        # The source directory is generated from development+negative definitions only.
        fixtures = self.private / "fixtures"
        generated = subprocess.run(
            [
                str(self.root / "backend/.venv/bin/python"),
                "-m",
                "mediflow.processing",
                "fixtures",
                "evaluation/fixtures/v1",
                "--output",
                str(fixtures),
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.save("fixture-generation.log", generated.stdout + generated.stderr)
        if generated.returncode:
            raise RuntimeError("Development-only fixture generation failed; inspect private log")
        (smoke / "fixtures").mkdir(exist_ok=True)
        for path in fixtures.glob("*.pdf"):
            if not path.name.startswith(("dev-", "neg-", "supplemental-")):
                raise RuntimeError("Non-development fixture in source")
            shutil.copy2(path, smoke / "fixtures" / path.name)
        if len(list((smoke / "fixtures").glob("*.pdf"))) != 35:
            raise RuntimeError(
                "Expected precisely 35 synthetic development/negative/supplemental fixtures"
            )
        dockerfile = (
            context / "Dockerfile.worker"
        ).read_text() + "\nCOPY --chown=10001:10001 smoke /smoke\n"
        (context / "Dockerfile.smoke").write_text(dockerfile)
        image = state["registry_server"] + "/processing-smoke:" + state["spike_id"]
        self.docker_run(
            "build",
            "build",
            "--platform",
            "linux/amd64",
            "-f",
            str(context / "Dockerfile.smoke"),
            "-t",
            image,
            str(context),
            timeout=1200,
        )
        token = self.az(
            "registry-login-token",
            "acr",
            "login",
            "--name",
            state["registry"],
            "--expose-token",
        )
        self.docker_run(
            "registry-login",
            "login",
            state["registry_server"],
            "--username",
            "00000000-0000-0000-0000-000000000000",
            "--password-stdin",
            stdin=token["accessToken"],
        )
        try:
            self.docker_run("push", "push", image, timeout=1200)
        finally:
            self.docker_run("registry-logout", "logout", state["registry_server"])
        state["image"] = image
        self.save("state.json", state)
        print(
            "Final integrated Linux/amd64 worker built and pushed to private registry",
            flush=True,
        )

    def deploy(self) -> None:
        state = self.state()
        self.guard(state)
        group = self.group(state)
        environment_path = (
            group + "/providers/Microsoft.App/managedEnvironments/" + state["environment"]
        )
        environment = self.rest("environment-current", environment_path)
        properties = environment["properties"]
        if (
            properties.get("provisioningState") != "Succeeded"
            or properties.get("environmentMode") != "WorkloadProfiles"
        ):
            raise RuntimeError("Standard WorkloadProfiles environment is not ready")
        if properties.get("workloadProfiles") != [
            {"name": "Consumption", "workloadProfileType": "Consumption"}
        ]:
            raise RuntimeError("Only a Consumption workload profile is allowed")
        identity = state["identity_id"]
        job = {
            "location": state["region"],
            "tags": TAGS,
            "identity": {
                "type": "UserAssigned",
                "userAssignedIdentities": {identity: {}},
            },
            "properties": {
                "environmentId": environment_path,
                "workloadProfileName": "Consumption",
                "configuration": {
                    "triggerType": "Manual",
                    "replicaTimeout": 300,
                    "replicaRetryLimit": 0,
                    "manualTriggerConfig": {
                        "replicaCompletionCount": 1,
                        "parallelism": 1,
                    },
                    "registries": [{"server": state["registry_server"], "identity": identity}],
                },
                "template": {
                    "containers": [
                        {
                            "name": "ocr-probe",
                            "image": state["image"],
                            "command": ["python", "/smoke/runtime.py"],
                            "resources": {"cpu": 0.5, "memory": "1Gi"},
                            "env": [
                                {"name": key, "value": value}
                                for key, value in {
                                    "STORAGE_ACCOUNT": state["storage"],
                                    "SPIKE_ID": state["spike_id"],
                                    "IDENTITY_CLIENT_ID": state["identity_client_id"],
                                }.items()
                            ],
                        }
                    ]
                },
            },
        }
        self.rest(
            "job-create",
            group + "/providers/Microsoft.App/jobs/" + state["job"],
            "PUT",
            job,
        )
        print(
            "Manual job submitted at 0.5 vCPU / 1 GiB / 300 seconds / no platform retry",
            flush=True,
        )

    def start(self) -> None:
        state = self.state()
        self.guard(state)
        if "execution" in state:
            raise RuntimeError(
                "An execution is already recorded; inspect it before starting another"
            )
        path = self.group(state) + "/providers/Microsoft.App/jobs/" + state["job"]
        result = self.rest("execution-start", path + "/start", "POST", {})
        state["execution"] = result["name"]
        state["execution_started_at"] = datetime.now(UTC).isoformat()
        self.save("state.json", state)
        print("One bounded manual job execution started", flush=True)

    def status(self) -> dict[str, Any]:
        state = self.state()
        result = self.rest(
            "execution-status",
            self.group(state)
            + "/providers/Microsoft.App/jobs/"
            + state["job"]
            + "/executions/"
            + state["execution"],
        )
        print("Execution status:", result.get("properties", {}).get("status"), flush=True)
        return result

    def collect(self) -> None:
        state = self.state()
        status = self.status()
        if status.get("properties", {}).get("status") != "Succeeded":
            raise RuntimeError("Execution has not succeeded")
        destination = self.private / "azure-processing.json"
        self.az(
            "download-result",
            "storage",
            "blob",
            "download",
            "--account-name",
            state["storage"],
            "--container-name",
            "ocr-results",
            "--name",
            state["spike_id"] + ".json",
            "--file",
            str(destination),
            "--auth-mode",
            "login",
            "--overwrite",
            "true",
        )
        destination.chmod(0o600)
        report = json.loads(destination.read_text())
        if report.get("synthetic_expectations_passed") is not True:
            raise RuntimeError("Expected synthetic outcome checks did not pass")
        print(
            "Azure private synthetic report downloaded; all expectations passed",
            flush=True,
        )

    def cleanup(self) -> None:
        state = self.state()
        self.check_group(state)
        self.az(
            "cleanup-request",
            "group",
            "delete",
            "--name",
            state["group"],
            "--yes",
            "--no-wait",
        )
        print(
            "Tagged temporary group deletion requested; run cleanup-status until absent",
            flush=True,
        )

    def cleanup_status(self) -> None:
        state = self.state()
        exists = self.az("cleanup-exists", "group", "exists", "--name", state["group"])
        self.save(
            "cleanup-evidence.json",
            {
                "temporary_resource_group_exists": exists,
                "all_temporary_resources_deleted": not exists,
                "checked_at": datetime.now(UTC).isoformat(),
            },
        )
        print("All temporary Azure resources deleted:", not exists, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "init",
            "infrastructure",
            "build-push",
            "deploy",
            "start",
            "status",
            "collect",
            "cleanup",
            "cleanup-status",
        ),
    )
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--docker-binary", default="docker")
    parser.add_argument("--docker-host", default=os.environ.get("DOCKER_HOST"))
    args = parser.parse_args()
    probe = Probe(args.workspace, args.docker_binary, args.docker_host)
    try:
        getattr(probe, args.stage.replace("-", "_"))()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(
            str(error)
            if isinstance(error, RuntimeError)
            else "Cloud deadline exceeded; inspect ignored private logs"
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
