"""One isolated process group per document; no parser runs in the caller."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from mediflow.processing.models import Limits, ProcessingResult, rejected

_SLOT = threading.BoundedSemaphore(1)


def process_pdf(source: bytes, *, limits: Limits | None = None) -> ProcessingResult:
    """Extract page evidence without modifying input; sanitize errors, never log text.

    One document per Python caller at a time. Deploy one process/execution and max
    job parallelism one; this semaphore is not a distributed scheduling mechanism.
    Linux children additionally enforce address-space and CPU limits. The worker
    container must enforce a 1 GiB cgroup memory ceiling and 64 PID ceiling.
    """
    limits = limits or Limits()
    started = time.monotonic()

    def finish(result: ProcessingResult) -> ProcessingResult:
        return result.model_copy(update={"elapsed_seconds": time.monotonic() - started})

    if len(source) > limits.max_bytes:
        return finish(rejected(source, "over_size"))
    if not _SLOT.acquire(timeout=limits.deadline_seconds):
        return finish(rejected(source, "timeout", failed=True))
    try:
        with tempfile.TemporaryDirectory(prefix="mediflow-pdf-") as directory:
            root = Path(directory)
            (root / "source.pdf").write_bytes(source)
            (root / "limits.json").write_text(limits.model_dump_json())
            environment = dict(os.environ, OMP_THREAD_LIMIT="1", OMP_NUM_THREADS="1")
            child = subprocess.Popen(
                [sys.executable, "-m", "mediflow.processing.child", str(root)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=environment,
            )
            try:
                remaining = max(0.001, limits.deadline_seconds - (time.monotonic() - started))
                child.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                _kill_group(child.pid)
                child.wait()
                return finish(rejected(source, "timeout", failed=True))
            finally:
                # Also remove remaining OCR descendants after any child exit.
                _kill_group(child.pid)
                child.wait()
            output = root / "result.json"
            if child.returncode != 0 or not output.exists() or output.stat().st_size > 8_000_000:
                return finish(rejected(source, "resource_limit", failed=True))
            try:
                result = ProcessingResult.model_validate(json.loads(output.read_text()))
            except (ValueError, OSError):
                return finish(rejected(source, "processing_failed", failed=True))
            return finish(result)
    except OSError:
        return finish(rejected(source, "processing_failed", failed=True))
    finally:
        _SLOT.release()


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
