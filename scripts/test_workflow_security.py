from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_workflow_security import verify_workflows


class WorkflowSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        source = Path(__file__).resolve().parents[1] / ".github" / "workflows"
        shutil.copytree(source, self.repository / ".github" / "workflows")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def mutate(self, workflow: str, old: str, new: str) -> None:
        path = self.repository / ".github" / "workflows" / workflow
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def assert_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            verify_workflows(self.repository)

    def test_current_workflows_pass(self) -> None:
        verify_workflows(self.repository)

    def test_equivalent_inline_jobs_comments_are_accepted(self) -> None:
        self.mutate("ci.yml", "jobs:\n", "jobs: # launcher checks\n")
        self.mutate("release.yml", "jobs:\n", "jobs: # publication graph\n")
        verify_workflows(self.repository)

    def test_renamed_status_context_is_rejected(self) -> None:
        self.mutate("ci.yml", "name: node launcher", "name: renamed node launcher")
        self.assert_rejected()

    def test_runtime_change_hidden_by_comment_is_rejected(self) -> None:
        self.mutate(
            "ci.yml",
            'python-version: "3.11"',
            'python-version: "3.12" # python-version: "3.11"',
        )
        self.assert_rejected()

    def test_false_action_version_metadata_is_rejected(self) -> None:
        self.mutate("ci.yml", "# v7.0.1", "# v6.0.0")
        self.assert_rejected()

    def test_mutable_action_reference_is_rejected(self) -> None:
        self.mutate(
            "ci.yml",
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/checkout@v7",
        )
        self.assert_rejected()

    def test_preflight_dependency_removal_is_rejected(self) -> None:
        self.mutate("release.yml", "  build:\n    needs: preflight\n", "  build:\n")
        self.assert_rejected()

    def test_manual_dispatch_condition_bypass_is_rejected(self) -> None:
        self.mutate(
            "release.yml",
            "  npm:\n    needs: preflight\n    if: github.event_name == 'push'\n",
            "  npm:\n    needs: preflight\n",
        )
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
