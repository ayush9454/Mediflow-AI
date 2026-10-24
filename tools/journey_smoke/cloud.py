"""Run-isolated hosted acceptance for all three roles. No canned results."""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patient_smoke.cloud import Probe as PatientProbe  # noqa: E402


class Probe(PatientProbe):
    private_directory = ".tooling/issue-12/azure"
    fixture_ticket = "ticket12"
    ownership_tags = {"project": "mediflow", "purpose": "issue-12-journey", "temporary": "true"}

    def provisioning(self):
        state = self.state()
        self.guard(state)
        statuses = {}
        for name, path, version in (
            (
                "environment",
                "/providers/Microsoft.App/managedEnvironments/" + state["environment"],
                "2026-07-01",
            ),
            (
                "storage",
                "/providers/Microsoft.Storage/storageAccounts/" + state["storage"],
                "2023-05-01",
            ),
        ):
            response = self.rest(name + "-provisioning", self.group(state) + path, version=version)
            statuses[name] = response["properties"]["provisioningState"]
        print(json.dumps(statuses), flush=True)

    def executions(self):
        state = self.state()
        self.guard(state)
        for label, name in (("worker", state["job"]), ("reconciler", "patient-reconciler")):
            path = self.group(state) + "/providers/Microsoft.App/jobs/" + name
            job = self.rest(label + "-status", path)
            executions = self.rest(label + "-executions", path + "/executions")
            print(
                json.dumps(
                    {
                        "job": label,
                        "provisioning": job["properties"].get("provisioningState"),
                        "executions": [
                            {
                                key: item.get("properties", {}).get(key)
                                for key in ("status", "startTime", "endTime")
                            }
                            for item in executions.get("value", [])
                        ],
                    }
                ),
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "init",
            "provisioning",
            "executions",
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
    parser.add_argument("--docker-binary", default="docker")
    parser.add_argument("--docker-host", default=None)
    args = parser.parse_args()
    probe = Probe(Path(__file__).resolve().parents[2], args.docker_binary, args.docker_host)
    try:
        getattr(probe, args.stage.replace("-", "_"))()
    except Exception:
        probe.save("last-stage-error.log", traceback.format_exc())
        parser.exit(2, "Journey stage failed; inspect ignored private responses.\n")


if __name__ == "__main__":
    main()
