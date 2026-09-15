import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.publish_from_instance import (
    apply_mod_plan,
    build_mod_plan,
    normalize_metadata_text,
    publish,
    restore_repository,
)


class PublishFromInstanceTest(unittest.TestCase):
    def test_plans_all_added_and_removed_mods(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, instance = make_layout(Path(directory))
            write_mod(instance, "kept.jar", b"kept")
            write_mod(instance, "new-library.jar", b"library")
            write_metadata(repo / "mods/kept.pw.toml", "kept.jar", b"kept")
            write_metadata(repo / "mods/removed.pw.toml", "removed.jar", b"removed")
            write_metadata(instance / "mods/.index/new-library.pw.toml", "new-library.jar", b"library")

            plan = build_mod_plan(repo, instance, set())

            self.assertEqual(["new-library.jar"], [change.filename for change in plan.added])
            self.assertEqual(["removed.jar"], [change.filename for change in plan.removed])
            self.assertEqual([], plan.unresolved)

            apply_mod_plan(plan)
            self.assertTrue((repo / "mods/new-library.pw.toml").is_file())
            self.assertFalse((repo / "mods/removed.pw.toml").exists())

    def test_reports_every_unresolved_mod(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, instance = make_layout(Path(directory))
            write_mod(instance, "unknown-a.jar", b"a")
            write_mod(instance, "unknown-b.jar", b"b")

            plan = build_mod_plan(repo, instance, set())

            self.assertEqual(["unknown-a.jar", "unknown-b.jar"], plan.unresolved)

    def test_updates_metadata_in_place_when_source_metadata_has_another_name(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, instance = make_layout(Path(directory))
            write_mod(instance, "changed.jar", b"new")
            write_metadata(repo / "mods/original-name.pw.toml", "changed.jar", b"old")
            write_metadata(instance / "mods/.index/new-name.pw.toml", "changed.jar", b"new")

            plan = build_mod_plan(repo, instance, set())
            apply_mod_plan(plan)

            self.assertEqual(["changed.jar"], [change.filename for change in plan.updated])
            self.assertTrue((repo / "mods/original-name.pw.toml").is_file())
            self.assertFalse((repo / "mods/new-name.pw.toml").exists())
            self.assertIn(
                hashlib.sha256(b"new").hexdigest(),
                (repo / "mods/original-name.pw.toml").read_text(encoding="utf-8"),
            )

    def test_rejects_stale_instance_metadata_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, instance = make_layout(Path(directory))
            write_mod(instance, "changed.jar", b"new bytes")
            write_metadata(instance / "mods/.index/changed.pw.toml", "changed.jar", b"old bytes")

            plan = build_mod_plan(repo, instance, set())

            self.assertEqual(["changed.jar (metadata hash mismatch)"], plan.unresolved)
            self.assertEqual([], plan.added)

    def test_preserves_declared_local_only_mod(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, instance = make_layout(Path(directory))
            write_mod(instance, "private.jar", b"private")

            plan = build_mod_plan(repo, instance, {"private.jar"})

            self.assertEqual([], plan.unresolved)
            self.assertEqual([], plan.added)

    def test_normalizes_prism_metadata_for_packwiz_installer(self):
        source = (
            "filename = 'example.jar'\n"
            "side = 'server'\n"
            "[download]\n"
            "hash = 'abc'\n"
            "mode = 'metadata:curseforge'\n"
            "url = ''\n"
        )

        normalized = normalize_metadata_text(source)

        self.assertIn("side = 'both'", normalized)
        self.assertNotIn("url = ''", normalized)

    def test_missing_instance_mod_directory_aborts_instead_of_planning_removals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "mods").mkdir(parents=True)
            write_metadata(repo / "mods/existing.pw.toml", "existing.jar", b"existing")

            with self.assertRaisesRegex(ValueError, "Instanz-Modverzeichnis fehlt"):
                build_mod_plan(repo, root / "mistyped-instance", set())

    def test_missing_instance_cli_error_has_no_traceback(self):
        script = Path(__file__).resolve().parents[1] / "tools/publish_from_instance.py"
        result = subprocess.run(
            [sys.executable, str(script), "0.15.2", "--dry-run", "--instance", "/tmp/does-not-exist"],
            text=True,
            capture_output=True,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("FEHLER: Instanz-Modverzeichnis fehlt", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_version_cannot_mutate_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, instance = make_layout(Path(directory))
            write_mod(instance, "new.jar", b"new")
            write_metadata(instance / "mods/.index/new.pw.toml", "new.jar", b"new")
            initialize_git_repository(repo)

            with self.assertRaisesRegex(ValueError, "Ungültige Packversion"):
                publish(repo, instance, "not-a-version", True)

            self.assertFalse((repo / "mods/new.pw.toml").exists())
            self.assertEqual("", git(repo, "status", "--porcelain"))

    def test_failed_publication_restore_removes_added_and_restores_deleted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, _ = make_layout(Path(directory))
            old = repo / "mods/old.pw.toml"
            write_metadata(old, "old.jar", b"old")
            (repo / "pack.toml").write_text('version = "0.15.0"\n', encoding="utf-8")
            initialize_git_repository(repo)

            old.unlink()
            (repo / "mods/new.pw.toml").write_text("new", encoding="utf-8")
            (repo / "pack.toml").write_text('version = "broken"\n', encoding="utf-8")
            git(repo, "add", "-A")

            restore_repository(repo, [Path("mods/new.pw.toml")])

            self.assertTrue(old.is_file())
            self.assertFalse((repo / "mods/new.pw.toml").exists())
            self.assertEqual('version = "0.15.0"\n', (repo / "pack.toml").read_text(encoding="utf-8"))
            self.assertEqual("", git(repo, "status", "--porcelain"))


def make_layout(root: Path) -> tuple[Path, Path]:
    repo = root / "repo"
    instance = root / "instance"
    (repo / "mods").mkdir(parents=True)
    (instance / "mods/.index").mkdir(parents=True)
    return repo, instance


def write_mod(instance: Path, filename: str, content: bytes) -> None:
    (instance / "mods" / filename).write_bytes(content)


def write_metadata(path: Path, filename: str, content: bytes) -> None:
    digest = hashlib.sha256(content).hexdigest()
    path.write_text(
        f'name = "Test"\nfilename = "{filename}"\nside = "both"\n\n'
        f'[download]\nhash-format = "sha256"\nhash = "{digest}"\n'
        f'url = "https://example.invalid/{filename}"\n',
        encoding="utf-8",
    )


def initialize_git_repository(repo: Path) -> None:
    (repo / ".baseline").write_text("test\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "baseline")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()


if __name__ == "__main__":
    unittest.main()
