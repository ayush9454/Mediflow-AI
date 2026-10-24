"""Temporary real patient-workflow deployment. All identities/secrets stay private."""

import argparse
import copy
import json
import secrets
import shlex
import shutil
import sys
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path

from google.auth import load_credentials_from_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "jobs_smoke"))
from cloud import Probe as JobProbe

TAGS = {"project": "mediflow", "purpose": "issue-09-patient-smoke", "temporary": "true"}


class Probe(JobProbe):
    def __init__(self, root, docker_binary, docker_host):
        super().__init__(root, docker_binary, docker_host)
        self.private = root / ".tooling/issue-9/azure"
        self.private.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.tags = TAGS

    def init(self):
        if (self.private / "state.json").exists():
            raise RuntimeError("State already exists; resume or clean this deployment")
        self.check_subscription()
        suffix = secrets.token_hex(3)
        state = {
            "group": "mediflow-patient-" + suffix,
            "registry": "mfpatient" + suffix,
            "storage": "mfpatient" + suffix,
            "identity": "patient-identity",
            "environment": "patient-consumption",
            "job": "patient-worker",
            "app": "patient-api",
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
        print("Temporary patient workflow group created; spending protection On", flush=True)

    def build_push(self):
        state = self.state()
        self.guard(state)
        context = self.private / "build"
        context.mkdir(exist_ok=True)
        for name in ("pyproject.toml", "uv.lock", "Dockerfile.worker"):
            shutil.copy2(self.root / "backend" / name, context / name)
        shutil.copytree(self.root / "backend/src", context / "src", dirs_exist_ok=True)
        image = state["registry_server"] + "/patient-workflow:" + state["spike_id"]
        self.docker_run(
            "build",
            "build",
            "--platform",
            "linux/amd64",
            "-f",
            str(context / "Dockerfile.worker"),
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
        metadata = self.az(
            "image",
            "acr",
            "repository",
            "show",
            "--name",
            state["registry"],
            "--image",
            "patient-workflow:" + state["spike_id"],
        )
        state["image"] = state["registry_server"] + "/patient-workflow@" + metadata["digest"]
        self.save("state.json", state)
        print("Real API/worker image pushed privately and pinned by digest", flush=True)

    def deploy(self):
        state = self.state()
        self.guard(state)
        credentials, project = self.google()
        # A real, short-lived owner token; no refresh credential or service-account
        # private key is transferred to Azure. Refresh by rerunning deploy if needed.
        adc = {
            "type": "authorized_user",
            "client_id": "temporary-no-refresh",
            "client_secret": "",
            "refresh_token": "",
            "token": credentials.token,
            "expiry": credentials.expiry.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        }
        loaded, _ = load_credentials_from_dict(adc)
        if not loaded.valid:
            raise RuntimeError("Temporary Google credential is not valid")
        values = {}
        for line in (self.root / ".tooling/issue-1/.env").read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep:
                words = shlex.split(value, comments=True)
                if len(words) == 1:
                    values[key.strip()] = words[0]
        if (
            values.get("GEMINI_USAGE_TIER") != "free"
            or values.get("GEMINI_MODEL_FREE_TIER_CONFIRMED") != "yes"
        ):
            raise RuntimeError("Existing free-tier confirmation required")
        job = self.job_template()
        props = job["properties"]
        config = props["configuration"]
        config.pop("manualTriggerConfig", None)
        config.update(
            triggerType="Event",
            replicaTimeout=420,
            secrets=[
                {"name": "google-adc", "value": json.dumps(adc)},
                {"name": "gemini-key", "value": values["GEMINI_API_KEY"]},
            ],
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
        environment = [
            {"name": key, "value": value}
            for key, value in {
                "MEDIFLOW_ENV": "production",
                "MEDIFLOW_FIREBASE_PROJECT_ID": project,
                "MEDIFLOW_AZURE_STORAGE_ACCOUNT_URL": f"https://{state['storage']}.blob.core.windows.net",
                "MEDIFLOW_AZURE_QUEUE_NAME": "report-processing",
                "AZURE_CLIENT_ID": state["identity_client_id"],
                "GOOGLE_APPLICATION_CREDENTIALS": "/secrets/google-adc.json",
            }.items()
        ]
        container = props["template"]["containers"][0]
        container.update(
            name="worker",
            command=["python", "-m", "mediflow.worker"],
            env=environment
            + [
                {"name": "MEDIFLOW_GEMINI_MODEL", "value": "gemini-3.5-flash-lite"},
                {"name": "MEDIFLOW_GEMINI_FREE_TIER_CONFIRMED", "value": "true"},
                {"name": "GEMINI_API_KEY", "secretRef": "gemini-key"},
            ],
            volumeMounts=[{"volumeName": "google", "mountPath": "/secrets"}],
        )
        props["template"]["volumes"] = [
            {
                "name": "google",
                "storageType": "Secret",
                "secrets": [{"secretRef": "google-adc", "path": "google-adc.json"}],
            }
        ]
        self.rest(
            "worker-deploy",
            self.group(state) + "/providers/Microsoft.App/jobs/" + state["job"],
            "PUT",
            job,
        )
        scheduled = copy.deepcopy(job)
        scheduled["properties"]["configuration"].pop("eventTriggerConfig")
        scheduled["properties"]["configuration"]["secrets"] = [
            {"name": "google-adc", "value": json.dumps(adc)}
        ]
        scheduled["properties"]["configuration"].update(
            triggerType="Schedule",
            replicaTimeout=120,
            scheduleTriggerConfig={
                "cronExpression": "*/5 * * * *",
                "parallelism": 1,
                "replicaCompletionCount": 1,
            },
        )
        scheduled["properties"]["template"]["containers"][0].update(
            command=["python", "-m", "mediflow.worker", "--reconcile"], env=environment
        )
        self.rest(
            "reconciler-deploy",
            self.group(state) + "/providers/Microsoft.App/jobs/patient-reconciler",
            "PUT",
            scheduled,
        )
        api_container = copy.deepcopy(container)
        api_container.update(
            name="api",
            command=[
                "python",
                "-m",
                "uvicorn",
                "mediflow.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-access-log",
            ],
            env=environment,
        )
        app = {
            "location": state["region"],
            "tags": self.tags,
            "identity": job["identity"],
            "properties": {
                "environmentId": props["environmentId"],
                "workloadProfileName": "Consumption",
                "configuration": {
                    "activeRevisionsMode": "Single",
                    "secrets": [{"name": "google-adc", "value": json.dumps(adc)}],
                    "registries": config["registries"],
                    "ingress": {
                        "external": True,
                        "targetPort": 8000,
                        "transport": "auto",
                        "allowInsecure": False,
                    },
                },
                "template": {
                    "containers": [api_container],
                    "volumes": props["template"]["volumes"],
                    "scale": {
                        "minReplicas": 0,
                        "maxReplicas": 1,
                        "rules": [
                            {"name": "http", "http": {"metadata": {"concurrentRequests": "2"}}}
                        ],
                    },
                },
            },
        }
        self.rest(
            "api-deploy",
            self.group(state) + "/providers/Microsoft.App/containerApps/" + state["app"],
            "PUT",
            app,
        )
        state["google_token_expires_at"] = adc["expiry"]
        self.save("state.json", state)
        self.status()

    def status(self):
        state = self.state()
        response = self.rest(
            "api-status",
            self.group(state) + "/providers/Microsoft.App/containerApps/" + state["app"],
        )
        properties = response["properties"]
        fqdn = ((properties.get("configuration") or {}).get("ingress") or {}).get("fqdn")
        if not fqdn:
            print("Hosted API provisioning:", properties.get("provisioningState"), flush=True)
            return
        state["api_url"] = "https://" + fqdn
        self.save("state.json", state)
        public = json.loads((self.root / ".tooling/issue-4/runtime-settings.json").read_text())
        self.save(
            "app-defines.json",
            {
                "API_BASE_URL": state["api_url"],
                "FIREBASE_API_KEY": public["firebaseApiKey"],
                "ENABLE_ROLE_PREVIEW": False,
            },
        )
        print(
            "Hosted endpoint saved privately; worker and recovery schedule deployed",
            flush=True,
        )

    def replicas(self):
        state = self.state()
        path = self.group(state) + "/providers/Microsoft.App/containerApps/" + state["app"]
        app = self.rest("api-current", path)
        revision = app["properties"]["latestRevisionName"]
        replicas = self.rest("api-replicas", path + "/revisions/" + revision + "/replicas")
        count = len(replicas.get("value", []))
        self.save(
            "replica-evidence.json",
            {"running_replicas": count, "checked_at": datetime.now(UTC).isoformat()},
        )
        print("Hosted API running replicas:", count, flush=True)

    def database(self):
        from google.cloud import firestore

        credentials, project = self.google()
        return firestore.Client(project=project, credentials=credentials)

    def cleanup(self):
        # Only reports with this deployment's unpredictable fixture prefix qualify.
        from google.cloud.firestore_v1.base_query import FieldFilter

        db = self.database()
        state = self.state()
        prefix = "ticket09-" + state["spike_id"][:12]
        reports = list(
            db.collection("reports")
            .where(filter=FieldFilter("fileName", ">=", prefix))
            .where(filter=FieldFilter("fileName", "<", prefix + "\uffff"))
            .limit(20)
            .stream(timeout=20)
        )
        for snapshot in reports:
            record = snapshot.to_dict()
            report_id = snapshot.id
            for collection in ("analyses", "processingJobs", "jobDispatches", "uploadHashes"):
                for item in (
                    db.collection(collection)
                    .where(filter=FieldFilter("reportId", "==", report_id))
                    .stream(timeout=20)
                ):
                    if collection == "processingJobs":
                        slot = db.collection("jobWorkerSlots").document(record["hospitalId"]).get()
                        if slot.exists and slot.to_dict().get("jobId") == item.id:
                            slot.reference.delete()
                        for related in ("jobAttempts", "analysisCommits"):
                            for child in (
                                db.collection(related)
                                .where(filter=FieldFilter("jobId", "==", item.id))
                                .stream(timeout=20)
                            ):
                                child.reference.delete()
                    item.reference.delete()
            # Remove only this upload's reservation without overwriting other uploads.
            from google.cloud import firestore

            reservation = db.collection("uploadReservations").document(record["hospitalId"])

            @firestore.transactional
            def release(transaction, reservation=reservation, report_id=report_id):
                current = reservation.get(transaction=transaction)
                if current.exists and report_id in current.to_dict().get("items", {}):
                    transaction.update(reservation, {"items." + report_id: firestore.DELETE_FIELD})

            release(db.transaction())
            session = db.collection("uploadSessions").document(report_id).get()
            if session.exists:
                index = session.to_dict().get("indexKey")
                if index:
                    db.collection("uploadKeys").document(index).delete()
            for collection, key in (
                ("cases", record["caseId"]),
                ("reports", report_id),
                ("uploadSessions", report_id),
                ("jobHeads", report_id),
            ):
                db.collection(collection).document(key).delete()
        # Group deletion is ownership-tag checked by the shared probe. Real quota
        # and minimal audit records remain truthful; no seeded account is removed.
        from container_job_probe import ContainerJobProbe

        self.save(
            "firestore-cleanup.json",
            {
                "report_count": len(reports),
                "payloads_deleted": True,
                "checked_at": datetime.now(UTC).isoformat(),
            },
        )
        ContainerJobProbe.cleanup(self)
        print(
            "This run's synthetic payloads removed; existing users and quotas retained",
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "init",
            "infrastructure",
            "build-push",
            "deploy",
            "status",
            "replicas",
            "cleanup",
            "cleanup-status",
        ),
    )
    parser.add_argument("--docker-binary", default="/Volumes/Ayush_External/homebrew/bin/docker")
    parser.add_argument(
        "--docker-host", default="unix:///Users/ayushsingh/.colima/mediflow/docker.sock"
    )
    args = parser.parse_args()
    try:
        probe = Probe(Path(__file__).resolve().parents[2], args.docker_binary, args.docker_host)
        getattr(probe, args.stage.replace("-", "_"))()
    except Exception:  # noqa: BLE001 — suppress credentials in provider exceptions
        probe.save("last-stage-error.log", traceback.format_exc())
        parser.exit(2, "Patient workflow stage failed; inspect ignored private responses.\n")


if __name__ == "__main__":
    main()
