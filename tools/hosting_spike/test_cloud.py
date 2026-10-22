"""Ensure cloud mutations stay inside the explicitly protected temporary scope."""

import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("cloud_probe", Path(__file__).with_name("cloud.py"))
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class ScopeTests(TestCase):
    def test_disabled_or_unprotected_subscription_stops_before_group_access(self):
        for state, spending in (("Enabled", "Off"), ("Disabled", "On")):
            with (
                self.subTest(state=state, spending=spending),
                patch.object(cloud, "scope", return_value="/subscriptions/synthetic"),
                patch.object(
                    cloud,
                    "rest",
                    return_value={
                        "state": state,
                        "subscriptionPolicies": {"spendingLimit": spending},
                    },
                ),
                patch.object(cloud, "az") as cli,
            ):
                with self.assertRaises(RuntimeError):
                    cloud.guard({"resourceGroup": "synthetic"})
                cli.assert_not_called()

    def test_cleanup_refuses_a_group_without_ownership_tags(self):
        with patch.object(cloud, "az", return_value={"tags": {}}) as cli:
            with self.assertRaises(RuntimeError):
                cloud.cleanup({"resourceGroup": "synthetic"})
            self.assertEqual(cli.call_count, 1)
            self.assertEqual(cli.call_args.args[1:3], ("group", "show"))

    def test_cleanup_targets_only_the_recorded_owned_group(self):
        with patch.object(cloud, "az", return_value={"tags": cloud.TAGS}) as cli:
            with redirect_stdout(io.StringIO()):
                cloud.cleanup({"resourceGroup": "synthetic"})
            self.assertEqual(cli.call_count, 2)
            self.assertEqual(
                cli.call_args.args,
                (
                    "cleanup-delete",
                    "group",
                    "delete",
                    "--name",
                    "synthetic",
                    "--yes",
                    "--no-wait",
                ),
            )


if __name__ == "__main__":
    main()
