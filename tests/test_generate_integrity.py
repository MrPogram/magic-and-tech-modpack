import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.generate_integrity import build_manifest


class GenerateIntegrityTest(unittest.TestCase):
    def test_builds_complete_manifest_and_rejects_unknown_mod(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            instance = root / "instance"
            (repo / "mods").mkdir(parents=True)
            (repo / "config").mkdir()
            (instance / "mods").mkdir(parents=True)
            (instance / "config").mkdir()
            (repo / "pack.toml").write_text('version = "0.15.0"\n', encoding="utf-8")

            (repo / "mods/example.pw.toml").write_text(
                'name = "Example"\nfilename = "example.jar"\nside = "both"\n'
                '[download]\nurl = "https://example.invalid/example.jar"\n'
                'hash-format = "sha256"\nhash = "' + "0" * 64 + '"\n',
                encoding="utf-8",
            )
            (instance / "mods/example.jar").write_bytes(b"managed")
            (instance / "mods/local.jar").write_bytes(b"local")
            (repo / "config/game.toml").write_text("enabled=true\n", encoding="utf-8")
            (instance / "config/game.toml").write_text("enabled=true\n", encoding="utf-8")

            manifest = build_manifest(repo, instance, ["mods/local.jar"], [])
            self.assertIn("file\tmanaged\t" + sha256(instance / "mods/example.jar"), manifest)
            self.assertIn("file\tmanaged\t" + sha256(instance / "config/game.toml"), manifest)
            self.assertIn("file\tlocal\t" + sha256(instance / "mods/local.jar"), manifest)

            (instance / "mods/unknown.jar").write_bytes(b"unknown")
            with self.assertRaisesRegex(ValueError, "Unexpected or missing files in mods"):
                build_manifest(repo, instance, ["mods/local.jar"], [])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
