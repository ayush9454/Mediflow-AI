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
    private_directory = ".tooling/issue-9/azure"
    fixture_ticket = "ticket09"
    ownership_tags = TAGS

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
        self.rest("api-revision", path + "/revisions/" + revision)
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

    def owned_reports(self, db):
        from google.cloud.firestore_v1.base_query import FieldFilter

        prefix = self.fixture_ticket + "-" + self.state()["spike_id"][:12]
        reports = list(
            db.collection("reports")
            .where(filter=FieldFilter("fileName", ">=", prefix))
            .where(filter=FieldFilter("fileName", "<", prefix + "\uffff"))
            .limit(51)
            .stream(timeout=20)
        )
        if len(reports) > 50:
            raise RuntimeError("Unexpected fixture count; inspect private state")
        return reports

    def owned_sessions(self, db):
        from google.cloud.firestore_v1.base_query import FieldFilter

        prefix = self.fixture_ticket + "-" + self.state()["spike_id"][:12]
        sessions = list(
            db.collection("uploadSessions")
            .where(filter=FieldFilter("request.fileName", ">=", prefix))
            .where(filter=FieldFilter("request.fileName", "<", prefix + "\uffff"))
            .limit(51)
            .stream(timeout=20)
        )
        if len(sessions) > 50:
            raise RuntimeError("Unexpected fixture session count")
        return sessions

    def collect(self):
        from google.cloud.firestore_v1.base_query import FieldFilter

        db = self.database()
        reports = self.owned_reports(db)
        jobs = [
            item.to_dict()
            for report in reports
            for item in db.collection("processingJobs")
            .where(filter=FieldFilter("reportId", "==", report.id))
            .stream(timeout=20)
        ]
        evidence = {
            "checked_at": datetime.now(UTC).isoformat(),
            "report_count": len(reports),
            "job_count": len(jobs),
            "processing_states": [report.to_dict()["processingStatus"] for report in reports],
            "job_states": [job["status"] for job in jobs],
            "attempt_counts": [job["attemptCount"] for job in jobs],
            "committed_analysis_count": sum(
                1
                for report in reports
                for _ in db.collection("analyses")
                .where(filter=FieldFilter("reportId", "==", report.id))
                .stream(timeout=20)
            ),
        }
        self.save("workflow-evidence.json", evidence)
        print(json.dumps(evidence), flush=True)

    def cleanup(self):
        from container_job_probe import ContainerJobProbe
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        db = self.database()
        reports = self.owned_reports(db)
        manifest_path = self.private / "firestore-cleanup-manifest.json"
        manifest = (
            json.loads(manifest_path.read_text())
            if manifest_path.exists()
            else {"paths": [], "reservations": [], "jobs": [], "reports": []}
        )
        paths = set(manifest["paths"])
        # Discover aliases independently; their canonical report may predate this
        # run and must never become part of our deletion scope.
        for session in self.owned_sessions(db):
            data = session.to_dict()
            paths.add(session.reference.path)
            paths.add("uploadGarbage/" + session.id)
            if data.get("indexKey"):
                paths.add("uploadKeys/" + data["indexKey"])
            manifest["reservations"].append([data["hospitalId"], session.id])
        for snapshot in reports:
            record = snapshot.to_dict()
            report_id = snapshot.id
            if record["processingStatus"] in {"validating", "queued", "processing"}:
                raise RuntimeError("Wait for run-owned processing to finish before cleanup")
            manifest["reports"].append(report_id)
            manifest["reservations"].append([record["hospitalId"], report_id])
            for collection in (
                "analyses",
                "reviews",
                "reviewIndex",
                "processingJobs",
                "jobDispatches",
                "uploadHashes",
                "uploadSessions",
            ):
                for item in (
                    db.collection(collection)
                    .where(filter=FieldFilter("reportId", "==", report_id))
                    .stream(timeout=20)
                ):
                    paths.add(item.reference.path)
                    if collection == "uploadSessions":
                        session = item.to_dict()
                        if session.get("indexKey"):
                            paths.add("uploadKeys/" + session["indexKey"])
                        paths.add("uploadGarbage/" + item.id)
                        manifest["reservations"].append([record["hospitalId"], item.id])
                    if collection == "processingJobs":
                        if item.to_dict()["status"] not in {"succeeded", "failed", "rejected"}:
                            raise RuntimeError("Run-owned job is not terminal; wait before cleanup")
                        manifest["jobs"].append([record["hospitalId"], item.id])
                        for related in ("jobAttempts", "analysisCommits"):
                            for child in (
                                db.collection(related)
                                .where(filter=FieldFilter("jobId", "==", item.id))
                                .stream(timeout=20)
                            ):
                                paths.add(child.reference.path)
                        for operation in (
                            db.collection("reprocessKeys")
                            .where(filter=FieldFilter("jobId", "==", item.id))
                            .stream(timeout=20)
                        ):
                            paths.add(operation.reference.path)
                        from mediflow.uploads import scoped_key

                        day = item.to_dict()["createdAt"][:10]
                        paths.add("reprocessQuotas/" + scoped_key(report_id, day))
                    if collection == "reviews":
                        for operation in (
                            db.collection("reviewKeys")
                            .where(filter=FieldFilter("reviewId", "==", item.id))
                            .stream(timeout=20)
                        ):
                            paths.add(operation.reference.path)
            for collection in ("assignmentKeys", "beginReviewKeys"):
                for operation in (
                    db.collection(collection)
                    .where(filter=FieldFilter("response.reportId", "==", report_id))
                    .stream(timeout=20)
                ):
                    paths.add(operation.reference.path)
            for collection, key in (
                ("cases", record["caseId"]),
                ("reports", report_id),
                ("uploadSessions", report_id),
                ("jobHeads", report_id),
                ("sourceArtifacts", report_id),
                ("uploadGarbage", report_id),
                ("approvedResults", report_id),
                ("reprocessRates", report_id),
            ):
                paths.add(collection + "/" + key)
        manifest["paths"] = sorted(paths)
        self.save("firestore-cleanup-manifest.json", manifest)
        for hospital_id, report_id in manifest["reservations"]:
            reservation = db.collection("uploadReservations").document(hospital_id)

            @firestore.transactional
            def release(transaction, reservation=reservation, report_id=report_id):
                current = reservation.get(transaction=transaction)
                if current.exists and report_id in current.to_dict().get("items", {}):
                    transaction.update(reservation, {"items." + report_id: firestore.DELETE_FIELD})

            release(db.transaction())
        for hospital_id, job_id in manifest["jobs"]:
            slot = db.collection("jobWorkerSlots").document(hospital_id)

            @firestore.transactional
            def release_slot(transaction, slot=slot, job_id=job_id):
                current = slot.get(transaction=transaction)
                if current.exists and current.to_dict().get("jobId") == job_id:
                    transaction.delete(slot)

            release_slot(db.transaction())
        for path in manifest["paths"]:
            db.document(path).delete()
        self.verify_payload_cleanup(db)
        # Exact-group deletion checks ownership tags. Quota and minimal audit
        # records remain truthful; no seeded account is removed.
        ContainerJobProbe.cleanup(self)
        print("Run-owned payloads removed; existing users and quotas retained", flush=True)

    def verify_payload_cleanup(self, db):
        from google.cloud.firestore_v1.base_query import FieldFilter

        manifest = json.loads((self.private / "firestore-cleanup-manifest.json").read_text())
        remaining = (
            sum(
                snapshot.exists
                for snapshot in db.get_all([db.document(path) for path in manifest["paths"]])
            )
            if manifest["paths"]
            else 0
        )
        reservations = sum(
            report_id
            in (
                db.collection("uploadReservations").document(hospital_id).get().to_dict() or {}
            ).get("items", {})
            for hospital_id, report_id in manifest["reservations"]
        )
        # Terminal jobs cannot commit again; still requery their report/job
        # references so a manifest alone never certifies absence of payloads.
        remaining += len(self.owned_reports(db)) + len(self.owned_sessions(db))
        for report_id in set(manifest["reports"]):
            for collection in ("analyses", "processingJobs", "jobDispatches", "uploadHashes"):
                remaining += sum(
                    1
                    for _ in db.collection(collection)
                    .where(filter=FieldFilter("reportId", "==", report_id))
                    .stream(timeout=20)
                )
        for _, job_id in manifest["jobs"]:
            for collection in ("jobAttempts", "analysisCommits"):
                remaining += sum(
                    1
                    for _ in db.collection(collection)
                    .where(filter=FieldFilter("jobId", "==", job_id))
                    .stream(timeout=20)
                )
        evidence = {
            "payloads_deleted": remaining == 0 and reservations == 0,
            "remaining_documents": remaining,
            "remaining_reservations": reservations,
            "checked_at": datetime.now(UTC).isoformat(),
        }
        self.save("firestore-cleanup.json", evidence)
        if not evidence["payloads_deleted"]:
            raise RuntimeError("Run-owned payloads remain")

    def cleanup_environment(self):
        # Retry only the exact empty, tagged run environment after group cleanup.
        state = self.state()
        self.guard(state)
        resources = self.az(
            "cleanup-retry-resources", "resource", "list", "--resource-group", state["group"]
        )
        expected = (
            self.group(state)
            + "/providers/Microsoft.App/managedEnvironments/"
            + state["environment"]
        )
        if any(item["id"].lower() != expected.lower() for item in resources):
            raise RuntimeError("Other run resources remain; use normal cleanup first")
        self.rest("environment-cleanup-retry", expected, "DELETE")
        print("Deletion retried for the exact empty temporary environment", flush=True)

    def cleanup_status(self):
        from container_job_probe import ContainerJobProbe

        ContainerJobProbe.cleanup_status(self)
        evidence = json.loads((self.private / "cleanup-evidence.json").read_text())
        if evidence["temporary_resource_group_exists"]:
            group = self.az("cleanup-progress", "group", "show", "--name", self.state()["group"])
            print(
                "Temporary group state:",
                group.get("properties", {}).get("provisioningState"),
                flush=True,
            )
            resources = self.az(
                "cleanup-remaining", "resource", "list", "--resource-group", self.state()["group"]
            )
            print(
                "Remaining resource types:",
                sorted({item["type"] for item in resources}),
                flush=True,
            )
            for item in resources:
                if item["type"].lower() == "microsoft.app/managedenvironments":
                    environment = self.rest("cleanup-environment-status", item["id"])
                    print(
                        "Environment state:",
                        environment.get("properties", {}).get("provisioningState"),
                        flush=True,
                    )
        self.verify_payload_cleanup(self.database())
        print("Run-owned Firestore payloads and reservations deleted: True", flush=True)


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
            "collect",
            "cleanup",
            "cleanup-status",
            "cleanup-environment",
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
