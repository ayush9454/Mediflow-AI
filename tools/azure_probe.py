"""Guarded Azure CLI, private probe state and scoped roles shared by temporary checks."""

import json
import os
import shlex
import subprocess
import uuid
from pathlib import Path
from typing import Any

API = "2026-07-01"


class AzureProbe:
    def __init__(self, root: Path, private_directory: str, tags: dict[str, str]):
        self.root = root.resolve()
        self.tags = tags
        self.private = self.root / private_directory
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
        if any(group.get("tags", {}).get(key) != value for key, value in self.tags.items()):
            raise RuntimeError("Temporary group ownership tags do not match")

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
