"""Staged, tagged temporary Azure OCR acceptance probe. Private state stays ignored.

Use --workspace when running from an isolated worktree against integrated source.
Stages: init, infrastructure, build-push, deploy, start, status, collect, cleanup,
cleanup-status. No stage converts subscriptions, enables registry admins, or creates
Log Analytics/private networking. Always finish cleanup and verify group absence.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_processing_report import AZURE_CONSUMPTION_CPU_QUOTAS, check  # noqa: E402
from container_job_probe import ContainerJobProbe  # noqa: E402

TAGS = {"project": "mediflow", "purpose": "issue-07-ocr-smoke", "temporary": "true"}
API = "2026-07-01"


class Probe(ContainerJobProbe):
    def __init__(self, root: Path, docker_binary: str, docker_host: str | None):
        super().__init__(
            root,
            ".tooling/issue-7/azure",
            TAGS,
            docker_binary,
            docker_host,
            result_container="ocr-results",
        )

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
            *(k + "=" + v for k, v in self.tags.items()),
        )
        print(
            "Fresh tagged OCR probe group created; spending protection verified On",
            flush=True,
        )

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
        shutil.copy2(
            self.root / "tools/check_processing_report.py", smoke / "check_processing_report.py"
        )
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
        repository = self.az(
            "registry-image",
            "acr",
            "repository",
            "show",
            "--name",
            state["registry"],
            "--image",
            "processing-smoke:" + state["spike_id"],
        )
        state["image_digest"] = repository["digest"]
        state["image"] = state["registry_server"] + "/processing-smoke@" + repository["digest"]
        self.save("state.json", state)
        print(
            "Final integrated Linux/amd64 worker built and pushed to private registry",
            flush=True,
        )

    def deploy(self) -> None:
        state = self.state()
        self.rest(
            "job-create",
            self.group(state) + "/providers/Microsoft.App/jobs/" + state["job"],
            "PUT",
            self.job_template(),
        )
        print("Manual OCR job submitted with bounded resources and no platform retry", flush=True)

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
        containers = status["properties"]["template"]["containers"]
        if len(containers) != 1 or any(
            containers[0]["resources"].get(key) != value
            for key, value in {"cpu": 0.5, "memory": "1Gi"}.items()
        ):
            raise RuntimeError("Expected actual Azure execution allocation of 0.5 vCPU / 1 GiB")
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
        check(report, allowed_cpu_max=AZURE_CONSUMPTION_CPU_QUOTAS)
        print(
            "Azure private synthetic report downloaded; all expectations passed",
            flush=True,
        )


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
