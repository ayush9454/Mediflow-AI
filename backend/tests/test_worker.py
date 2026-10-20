import json

import pytest

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
