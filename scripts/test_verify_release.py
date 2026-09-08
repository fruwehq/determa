from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_release import ReleaseVerificationError, verify_release


class VerifyReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        for directory in ("python", "rust", "node"):
            (self.repository / directory).mkdir()
        self.write_versions("1.2.3", "1.2.3", "1.2.3")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_versions(
        self,
        python_version: str,
        rust_version: str,
        node_version: str,
        *,
        lock_version: str | None = None,
        lock_root_version: str | None = None,
    ) -> None:
        (self.repository / "python" / "pyproject.toml").write_text(
            f'[project]\nversion = "{python_version}"\n'
        )
        (self.repository / "rust" / "Cargo.toml").write_text(
            f'[package]\nversion = "{rust_version}"\n'
        )
        (self.repository / "node" / "package.json").write_text(
            json.dumps({"version": node_version})
        )
        (self.repository / "node" / "package-lock.json").write_text(
            json.dumps(
                {
                    "version": lock_version or node_version,
                    "packages": {"": {"version": lock_root_version or node_version}},
                }
            )
        )

    def test_matching_stable_tag_passes(self) -> None:
        self.assertEqual(verify_release(self.repository, "push", "v1.2.3"), "v1.2.3")

    def test_manual_crates_release_still_requires_coherent_versions(self) -> None:
        self.assertEqual(verify_release(self.repository, "workflow_dispatch", None), "v1.2.3")

    def test_tag_must_match_exactly(self) -> None:
        for tag in ("1.2.3", "v1.2.4", "v01.2.3", "v1.2.3rc1", "v1.2.3\n"):
            with self.subTest(tag=tag), self.assertRaises(ReleaseVerificationError):
                verify_release(self.repository, "push", tag)

    def test_every_package_version_must_match(self) -> None:
        variants = (
            ("1.2.4", "1.2.3", "1.2.3", None, None),
            ("1.2.3", "1.2.4", "1.2.3", None, None),
            ("1.2.3", "1.2.3", "1.2.4", None, None),
            ("1.2.3", "1.2.3", "1.2.3", "1.2.4", None),
            ("1.2.3", "1.2.3", "1.2.3", None, "1.2.4"),
        )
        for python, rust, node, lock, lock_root in variants:
            with self.subTest(versions=(python, rust, node, lock, lock_root)):
                self.write_versions(
                    python, rust, node, lock_version=lock, lock_root_version=lock_root
                )
                with self.assertRaises(ReleaseVerificationError):
                    verify_release(self.repository, "push", "v1.2.3")

    def test_only_canonical_stable_versions_pass(self) -> None:
        for version in ("1.2", "1.2.3.4", "01.2.3", "1.02.3", "1.2.03", "1.2.3rc1", "１.2.3"):
            with self.subTest(version=version):
                self.write_versions(version, version, version)
                with self.assertRaises(ReleaseVerificationError):
                    verify_release(self.repository, "push", f"v{version}")

    def test_unknown_event_and_manual_tag_fail_closed(self) -> None:
        with self.assertRaises(ReleaseVerificationError):
            verify_release(self.repository, "schedule", None)
        with self.assertRaises(ReleaseVerificationError):
            verify_release(self.repository, "workflow_dispatch", "v1.2.3")


if __name__ == "__main__":
    unittest.main()
