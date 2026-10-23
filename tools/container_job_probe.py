"""Shared guarded infrastructure and templates for disposable Container Apps checks."""

import base64
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azure_probe import AzureProbe


class ContainerJobProbe(AzureProbe):
    def __init__(
        self,
        root: Path,
        private_directory: str,
        tags: dict[str, str],
        docker_binary: str,
        docker_host: str | None,
        *,
        result_container: str,
    ):
        super().__init__(root, private_directory, tags)
        self.result_container = result_container
        self.docker = [docker_binary] + (["--host", docker_host] if docker_host else [])
        docker_config = self.private / "docker-config"
        docker_config.mkdir(parents=True, exist_ok=True)
        docker_config.chmod(0o700)
        plugins = Path(docker_binary).absolute().parents[1] / "lib/docker/cli-plugins"
        if plugins.is_dir():
            (docker_config / "config.json").write_text(
                json.dumps({"cliPluginsExtraDirs": [str(plugins)]})
            )
        self.environment = dict(os.environ, DOCKER_CONFIG=str(docker_config))

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
                "tags": self.tags,
                "properties": {
                    "environmentMode": "WorkloadProfiles",
                    "workloadProfiles": [
                        {"name": "Consumption", "workloadProfileType": "Consumption"}
                    ],
                    "appLogsConfiguration": {"destination": None},
                },
            },
        )
        self.az(
            "registry-provider-register",
            "provider",
            "register",
            "--namespace",
            "Microsoft.ContainerRegistry",
            "--wait",
            timeout=600,
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
            *(k + "=" + v for k, v in self.tags.items()),
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
            {"location": state["region"], "tags": self.tags},
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
                "tags": self.tags,
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
            storage_path + "/blobServices/default/containers/" + self.result_container,
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

    def job_template(self) -> dict[str, Any]:
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
        profiles = properties.get("workloadProfiles", [])
        if len(profiles) != 1 or any(
            profiles[0].get(key) != "Consumption" for key in ("name", "workloadProfileType")
        ):
            raise RuntimeError("Only a Consumption workload profile is allowed")
        usage = self.az(
            "environment-quotas",
            "containerapp",
            "env",
            "list-usages",
            "--name",
            state["environment"],
            "--resource-group",
            state["group"],
        )
        rows = usage.get("value", []) if isinstance(usage, dict) else usage
        cores = [
            row
            for row in rows
            if row.get("name", {}).get("value") == "ManagedEnvironmentConsumptionCores"
        ]
        if not cores or cores[0]["limit"] - cores[0]["currentValue"] < 0.5:
            raise RuntimeError("At least 0.5 available Consumption cores is required")
        identity = state["identity_id"]
        job = {
            "location": state["region"],
            "tags": self.tags,
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
        return job
