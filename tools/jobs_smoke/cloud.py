"""Disposable student-protected queue/Firestore acceptance. Private state stays ignored."""

import argparse
import asyncio
import base64
import json
import os
import secrets
import shutil
import sys
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from azure.core.credentials import AccessToken
from google.auth import load_credentials_from_file
from google.auth.transport.requests import Request
from google.cloud import firestore
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from azure_probe import AzureProbe  # noqa: E402
from processing_smoke.cloud import Probe as ProcessingProbe  # noqa: E402
from runtime import NamespacedClient  # noqa: E402

from mediflow.contracts import Account, ReportRegistration  # noqa: E402
from mediflow.job_queue import AzureQueue  # noqa: E402
from mediflow.jobs import Jobs  # noqa: E402
from mediflow.uploads import Uploads  # noqa: E402
from mediflow.uploads.platform import BlobDocuments, FirestoreDatabase  # noqa: E402

TAGS = {"project": "mediflow", "purpose": "issue-06-jobs-smoke", "temporary": "true"}


class Probe(ProcessingProbe):
    def __init__(self, root, docker_binary, docker_host):
        AzureProbe.__init__(self, root, ".tooling/issue-6/azure", TAGS)
        self.docker = [docker_binary] + (["--host", docker_host] if docker_host else [])
        config = self.private / "docker-config"
        config.mkdir(exist_ok=True)
        config.chmod(0o700)
        plugins = Path(docker_binary).absolute().parents[1] / "lib/docker/cli-plugins"
        if plugins.is_dir():
            (config / "config.json").write_text(json.dumps({"cliPluginsExtraDirs": [str(plugins)]}))
        self.environment = dict(os.environ, DOCKER_CONFIG=str(config))

    def google(self):
        settings = json.loads((self.root / ".tooling/issue-4/runtime-settings.json").read_text())
        credentials, _ = load_credentials_from_file(
            str(self.root / ".tooling/issue-4/owner-adc.json"),
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        credentials.refresh(Request())
        return credentials, settings["projectId"]

    def database(self):
        credentials, project = self.google()
        client = firestore.Client(project=project, credentials=credentials)
        return NamespacedClient(client, self.state()["spike_id"])

    def init(self):
        if (self.private / "state.json").exists():
            raise RuntimeError("Existing state: resume or clean this probe")
        self.check_subscription()
        suffix = secrets.token_hex(3)
        state = {
            "group": "mediflow-jobs-" + suffix,
            "registry": "mfjobs" + suffix,
            "storage": "mfjobs" + suffix,
            "identity": "jobs-probe-identity",
            "environment": "jobs-consumption",
            "job": "jobs-probe",
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
        print("Temporary jobs group created; student spending protection On", flush=True)

    def infrastructure(self):
        super().infrastructure()
        state = self.state()
        storage = (
            self.group(state) + "/providers/Microsoft.Storage/storageAccounts/" + state["storage"]
        )
        for path, properties in (
            ("/queueServices/default/queues/report-processing", {}),
            ("/blobServices/default/containers/reports", {"publicAccess": "None"}),
        ):
            self.rest(
                "create-" + path.rsplit("/", 1)[1],
                storage + path,
                "PUT",
                {"properties": properties},
                version="2023-05-01",
            )
        self.role(
            "worker-queue",
            storage,
            state["identity_principal_id"],
            "974c5e8b-45b9-4653-ba55-5f855dd0fb88",
            "ServicePrincipal",
        )
        token = self.az(
            "owner-token",
            "account",
            "get-access-token",
            "--resource",
            "https://management.azure.com/",
        )
        payload = token["accessToken"].split(".")[1]
        owner = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["oid"]
        for name, role in (
            ("queue", "974c5e8b-45b9-4653-ba55-5f855dd0fb88"),
            ("blob", "ba92f5b4-2d11-453d-a403-e96b0029c9fe"),
        ):
            self.role("owner-" + name, storage, owner, role, "User")
        print("Private report Blob and queue ready with scoped identities", flush=True)

    def build_push(self):
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
        dockerfile = (
            context / "Dockerfile.worker"
        ).read_text() + "\nCOPY --chown=10001:10001 smoke /smoke\n"
        (context / "Dockerfile.smoke").write_text(dockerfile)
        image = state["registry_server"] + "/jobs-smoke:" + state["spike_id"]
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
            "registry-token", "acr", "login", "--name", state["registry"], "--expose-token"
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
            self.docker_run("logout", "logout", state["registry_server"])
        repository = self.az(
            "registry-image",
            "acr",
            "repository",
            "show",
            "--name",
            state["registry"],
            "--image",
            "jobs-smoke:" + state["spike_id"],
        )
        state["image"] = state["registry_server"] + "/jobs-smoke@" + repository["digest"]
        self.save("state.json", state)
        print("Actual worker image built and pushed privately", flush=True)

    def deploy(self):
        super().deploy(submit=False)
        state = self.state()
        job = json.loads((self.private / "job-create-request.json").read_text())
        credentials, project = self.google()
        config = job["properties"]["configuration"]
        config.pop("manualTriggerConfig", None)
        config.update(
            triggerType="Event",
            replicaTimeout=420,
            secrets=[{"name": "google-token", "value": credentials.token}],
            eventTriggerConfig={
                "replicaCompletionCount": 1,
                "parallelism": 1,
                "scale": {
                    "minExecutions": 0,
                    "maxExecutions": 1,
                    "pollingInterval": 30,
                    "rules": [
                        {
                            "name": "reports",
                            "type": "azure-queue",
                            "identity": state["identity_id"],
                            "metadata": {
                                "accountName": state["storage"],
                                "queueName": "report-processing",
                                "queueLength": "1",
                            },
                        }
                    ],
                },
            },
        )
        container = job["properties"]["template"]["containers"][0]
        container["env"] += [
            {"name": "MEDIFLOW_ENV", "value": "test"},
            {"name": "GOOGLE_PROJECT", "value": project},
            {"name": "GOOGLE_TOKEN", "secretRef": "google-token"},
        ]
        self.rest(
            "event-job-create",
            self.group(state) + "/providers/Microsoft.App/jobs/" + state["job"],
            "PUT",
            job,
        )
        # The same trusted code also runs on a schedule, independently of API traffic.
        config.pop("eventTriggerConfig")
        config.update(
            triggerType="Schedule",
            replicaTimeout=120,
            scheduleTriggerConfig={
                "cronExpression": "*/5 * * * *",
                "parallelism": 1,
                "replicaCompletionCount": 1,
            },
        )
        container["command"] += ["--reconcile"]
        self.rest(
            "scheduled-job-create",
            self.group(state) + "/providers/Microsoft.App/jobs/jobs-reconciler",
            "PUT",
            job,
        )
        print("Event worker and independent five-minute reconciler deployed", flush=True)

    def credential(self):
        probe = self

        class Credential:
            def get_token(self, *scopes, **kwargs):
                data = probe.az(
                    "storage-token",
                    "account",
                    "get-access-token",
                    "--resource",
                    "https://storage.azure.com/",
                )
                return AccessToken(data["accessToken"], int(data["expires_on"]))

        return Credential()

    def seed(self):
        state = self.state()
        self.guard(state)
        if "job_id" in state:
            raise RuntimeError("A job is already seeded; inspect it rather than creating another")
        database = FirestoreDatabase(self.database())
        uploads = Uploads(
            database,
            BlobDocuments(
                "https://" + state["storage"] + ".blob.core.windows.net",
                "reports",
                self.credential(),
            ),
        )
        output = BytesIO()
        pdf = canvas.Canvas(output, invariant=True)
        pdf.drawString(40, 750, "Synthetic laboratory report Result Reference interval")
        pdf.drawString(40, 720, "Glucose 92 mg/dL Reference range 70-100")
        pdf.save()
        source = output.getvalue()
        account = Account(
            uid="synthetic-patient",
            hospital_id="synthetic-hospital",
            display_name="Synthetic Patient",
            role="patient",
            active=True,
        )
        session = uploads.register(
            account,
            ReportRegistration(
                file_name="synthetic.pdf", byte_count=len(source), synthetic_data_acknowledged=True
            ),
            "cloud-test",
            "cloud-test",
        )

        async def chunks():
            yield source

        asyncio.run(uploads.upload(session.report.report_id, chunks(), "application/pdf"))
        job = uploads.complete(session.report.report_id, "cloud-test")
        state.update(job_id=job.job_id, report_id=job.report_id)
        self.save("state.json", state)
        print(
            "Accepted upload persisted without enqueue; scheduled reconciliation owns delivery",
            flush=True,
        )

    def collect(self):
        state = self.state()
        database = FirestoreDatabase(self.database())
        queue = AzureQueue(
            "https://" + state["storage"] + ".queue.core.windows.net",
            "report-processing",
            self.credential(),
        )
        jobs = Jobs(database, queue)
        job = jobs.get(state["job_id"])
        print("Durable job status:", job.status, flush=True)
        if job.status != "succeeded":
            return
        namespace = self.database()
        counts = {
            name: len(list(namespace.collection(name).stream(timeout=10)))
            for name in (
                "analyses",
                "analysisCommits",
                "jobAttempts",
                "processingJobs",
                "uploadQuotas",
            )
        }
        candidate = jobs.candidate(job.job_id)
        assert (
            counts["analyses"]
            == counts["analysisCommits"]
            == counts["jobAttempts"]
            == counts["processingJobs"]
            == 1
        )
        assert candidate.provenance.model_provider == "test-only"
        events = list(namespace.collection("auditEvents").stream(timeout=10))
        assert sum(e.to_dict().get("action") == "processing_succeeded" for e in events) == 1
        executions = self.rest(
            "worker-executions",
            self.group(state) + "/providers/Microsoft.App/jobs/" + state["job"] + "/executions",
        )
        assert any(e["properties"].get("status") == "Succeeded" for e in executions["value"])
        self.save(
            "evidence.json",
            {
                "checkedAt": datetime.now(UTC).isoformat(),
                "hostedQueueTriggered": True,
                "durableStatus": job.status,
                "attempts": job.attempt_count,
                "counts": counts,
                "testOnlyAdapter": True,
                "independentScheduledReconciliation": True,
            },
        )
        print("Hosted event execution and durable candidate/audit counts verified", flush=True)

    def cleanup(self):
        super().cleanup()
        client = self.database()
        client.db.recursive_delete(client.namespace)
        print("Disposable Firestore namespace removed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "init",
            "infrastructure",
            "build-push",
            "deploy",
            "seed",
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
    getattr(probe, args.stage.replace("-", "_"))()


if __name__ == "__main__":
    main()
