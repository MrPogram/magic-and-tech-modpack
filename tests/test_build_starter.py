import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_starter import build_starter


class BuildStarterTest(unittest.TestCase):
    def test_contains_only_bootstrap_and_required_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            instance = root / "minecraft"
            repo = root / "repo"
            (instance / "mods").mkdir(parents=True)
            (instance / "saves/world").mkdir(parents=True)
            (instance / "tacz/local-pack").mkdir(parents=True)
            repo.mkdir()
            (instance / "mods/local.jar").write_bytes(b"local")
            (instance / "tacz/local-pack/data.json").write_text("{}", encoding="utf-8")
            (instance / "saves/world/level.dat").write_bytes(b"private")
            (instance / "options.txt").write_text("private", encoding="utf-8")
            (repo / "integrity-manifest.tsv").write_text("magic-tech-integrity-v1\nversion\t1\n", encoding="utf-8")
            updater = root / "updater.jar"
            bootstrap = root / "bootstrap.jar"
            mmc = root / "mmc-pack.json"
            updater.write_bytes(b"updater")
            bootstrap.write_bytes(b"bootstrap")
            mmc.write_text("{}", encoding="utf-8")
            output = root / "starter.zip"

            build_starter(
                instance,
                repo,
                output,
                ["mods/local.jar"],
                ["tacz/local-pack"],
                updater,
                bootstrap,
                mmc,
            )

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("instance.cfg", names)
                self.assertIn("mmc-pack.json", names)
                self.assertIn(".minecraft/magic-tech-updater.jar", names)
                self.assertIn(".minecraft/packwiz-installer-bootstrap.jar", names)
                self.assertIn(".minecraft/mods/local.jar", names)
                self.assertIn(".minecraft/tacz/local-pack/data.json", names)
                self.assertIn(".minecraft/.magic-tech/integrity-manifest.tsv", names)
                self.assertNotIn(".minecraft/options.txt", names)
                self.assertFalse(any(name.startswith(".minecraft/saves/") for name in names))
                cfg = archive.read("instance.cfg").decode("utf-8")
                self.assertIn("PreLaunchCommand=\"$INST_JAVA\" -jar magic-tech-updater.jar", cfg)


if __name__ == "__main__":
    unittest.main()
