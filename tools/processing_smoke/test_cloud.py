"""Keep temporary OCR cloud mutations behind subscription and ownership guards."""

import importlib.util
import io
import json
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "processing_cloud_probe", Path(__file__).with_name("cloud.py")
)
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class GuardTests(TestCase):
    def make_probe(self, directory):
        root = Path(directory)
        settings = root / ".tooling/issue-1"
        settings.mkdir(parents=True)
        (settings / ".env").write_text("AZURE_SUBSCRIPTION_ID='synthetic-subscription'\n")
        return cloud.Probe(root, "docker", None)

    def test_disabled_or_unprotected_account_never_creates_a_resource_group(self):
        for state, spending in (("Disabled", "On"), ("Enabled", "Off")):
            with self.subTest(state=state, spending=spending), tempfile.TemporaryDirectory() as d:
                probe = self.make_probe(d)
                with patch.object(
                    cloud.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [],
                        0,
                        json.dumps(
                            {"state": state, "subscriptionPolicies": {"spendingLimit": spending}}
                        ),
                        "",
                    ),
                ) as execute:
                    with self.assertRaises(RuntimeError):
                        probe.init()
                self.assertEqual(execute.call_count, 1)
                self.assertFalse((probe.private / "state.json").exists())

    def test_cleanup_requires_ownership_and_targets_only_the_recorded_group(self):
        for tags, permitted in (({}, False), (cloud.TAGS, True)):
            with self.subTest(permitted=permitted), tempfile.TemporaryDirectory() as d:
                probe = self.make_probe(d)
                probe.save("state.json", {"group": "synthetic-ocr-group"})
                commands = []

                def execute(arguments, *, _commands=commands, _tags=tags, **kwargs):
                    _commands.append(arguments)
                    return subprocess.CompletedProcess(
                        arguments, 0, json.dumps({"tags": _tags}), ""
                    )

                with (
                    patch.object(cloud.subprocess, "run", side_effect=execute),
                    redirect_stdout(io.StringIO()),
                ):
                    if permitted:
                        probe.cleanup()
                    else:
                        with self.assertRaises(RuntimeError):
                            probe.cleanup()
                deletions = [command for command in commands if command[1:3] == ["group", "delete"]]
                self.assertEqual(len(deletions), int(permitted))
                if permitted:
                    self.assertIn("synthetic-ocr-group", deletions[0])


if __name__ == "__main__":
    main()
