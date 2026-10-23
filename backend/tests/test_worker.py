import json

import pytest
from test_jobs import accepted_job  # noqa: F401
from test_uploads import setup_uploads  # noqa: F401

from mediflow.worker import main


def test_worker_status_is_safe_and_explicit(monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "DO_NOT_PRINT_THIS")
    monkeypatch.setattr("sys.argv", ["worker", "--check-config"])
    assert main() == 0
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "not_ready"
    assert "DO_NOT_PRINT_THIS" not in output


def test_worker_cannot_pretend_to_process_jobs(monkeypatch):
    monkeypatch.setattr("sys.argv", ["worker"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_acknowledgement_failure_after_commit_does_not_repeat_processing(accepted):
    from test_jobs import candidate

    from mediflow.job_queue import Delivery
    from mediflow.worker import execute_one

    jobs, _, now, job, (_, uploads, _, _) = accepted

    class Queue:
        fail_ack = True
        acknowledged = False

        def receive(self):
            return Delivery(job["jobId"], "delivery", "receipt")

        def acknowledge(self, delivery):
            if self.fail_ack:
                raise OSError("lost acknowledgement")
            self.acknowledged = True

    class Processor:
        calls = 0

        def __call__(self, lease, source):
            self.calls += 1
            return candidate(lease, now[0])

    queue = Queue()
    processor = Processor()
    with pytest.raises(OSError):
        execute_one(jobs, queue, uploads, processor)
    assert jobs.get(job["jobId"]).status == "succeeded"
    queue.fail_ack = False
    assert execute_one(jobs, queue, uploads, processor)
    assert queue.acknowledged
    assert processor.calls == 1
    assert jobs.get(job["jobId"]).attempt_count == 1


def test_subprocess_adapter_is_explicitly_test_only_and_normal_worker_never_fabricates(accepted):
    from mediflow.contracts import ErrorCode
    from mediflow.job_processor import SubprocessProcessor
    from mediflow.worker import ProcessingFailure

    jobs, _, _, job, (_, uploads, _, _) = accepted
    lease = jobs.claim(job["jobId"])
    source = uploads.document(job["reportId"])
    for environment in ("production", "development"):
        with pytest.raises(ValueError):
            SubprocessProcessor(environment=environment, test_adapter=True)
    result = SubprocessProcessor(environment="test", test_adapter=True)(lease, source)
    assert result.rows == ()
    assert result.provenance.model_provider == "test-only"
    assert result.issues[0].code == "test_adapter"
    with pytest.raises(ProcessingFailure) as error:
        SubprocessProcessor(environment="test")(lease, source)
    assert error.value.code == ErrorCode.INTEGRATION_NOT_CONFIGURED
    assert not error.value.transient


@pytest.mark.parametrize("boundary", ["lease", "before_commit", "after_commit", "processing"])
def test_worker_interruption_boundaries_recover_without_duplicate_results(accepted, boundary):
    from datetime import timedelta

    from test_jobs import candidate

    from mediflow.job_queue import Delivery
    from mediflow.jobs import Jobs
    from mediflow.worker import execute_one

    jobs, _, now, job, (_, uploads, _, _) = accepted

    class Queue:
        acknowledged = False

        def receive(self):
            return Delivery(job["jobId"], "message", "receipt")

        def acknowledge(self, delivery):
            self.acknowledged = True

        def send(self, job_id):
            pass

    class InterruptedDatabase:
        interrupted = False

        def run(self, operation):
            if boundary == "lease" and not self.interrupted:
                self.interrupted = True
                raise ConnectionError("storage unavailable before acquisition")
            completed = False

            def transaction(tx):
                nonlocal completed
                result = operation(tx)
                completed = tx.get("processingJobs", job["jobId"])["status"] == "succeeded"
                if completed and boundary == "before_commit" and not self.interrupted:
                    self.interrupted = True
                    raise ConnectionError("transaction rolled back")
                return result

            result = jobs.database.run(transaction)
            if completed and boundary == "after_commit" and not self.interrupted:
                self.interrupted = True
                raise ConnectionError("commit response lost")
            return result

        def due(self, *args):
            return jobs.database.due(*args)

    class Processor:
        interrupted = False

        def __call__(self, lease, source):
            if boundary == "processing" and not self.interrupted:
                self.interrupted = True
                raise SystemExit("worker terminated")
            return candidate(lease, now[0])

    queue = Queue()
    recovering = Jobs(InterruptedDatabase(), queue, clock=lambda: now[0])
    processor = Processor()
    with pytest.raises((ConnectionError, SystemExit)):
        execute_one(recovering, queue, uploads, processor)
    assert not queue.acknowledged
    now[0] += timedelta(seconds=331)
    recovering.reconcile()
    now[0] += timedelta(seconds=120)
    assert execute_one(recovering, queue, uploads, processor)
    assert queue.acknowledged
    assert jobs.get(job["jobId"]).status == "succeeded"
    assert jobs.candidate(job["jobId"]) is not None
    assert jobs.get(job["jobId"]).attempt_count == (
        2 if boundary in {"processing", "before_commit"} else 1
    )
