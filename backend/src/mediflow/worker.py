"""Fail-closed worker entry point until the durable queue adapter is implemented."""

import argparse
import json

from mediflow.config import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description="MediFlow processing worker")
    parser.add_argument("--check-config", action="store_true", help="Print safe integration status")
    arguments = parser.parse_args()
    Settings.from_environment()
    status = {
        "status": "not_ready",
        "queueAdapter": "not_implemented",
        "documentAdapter": "not_implemented",
        "analysisAdapter": "not_implemented",
    }
    if arguments.check_config:
        print(json.dumps(status, sort_keys=True))
        return 0
    parser.exit(
        2, "Worker unavailable: durable queue and processing adapters are not implemented.\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
