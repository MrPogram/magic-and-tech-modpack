#!/usr/bin/env python3
import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.generate_integrity import DEFAULT_INSTANCE, DEFAULT_LOCAL_FILES, DEFAULT_LOCAL_TREES

INSTANCE_CFG = """[General]
AutomaticJava=true
ConfigVersion=1.3
InstanceType=OneSix
LogPrePostOutput=true
ManagedPack=false
MaxMemAlloc=8192
MinMemAlloc=4096
OverrideCommands=true
OverrideMemory=true
PreLaunchCommand=\"$INST_JAVA\" -jar magic-tech-updater.jar
iconKey=default
name=Magic and Tech
"""


def build_starter(
    instance: Path,
    repo: Path,
    output: Path,
    local_files: list[str],
    local_trees: list[str],
    updater: Path,
    bootstrap: Path,
    mmc_pack: Path,
) -> None:
    instance = instance.resolve()
    repo = repo.resolve()
    output = output.resolve()
    required = [updater, bootstrap, mmc_pack, repo / "integrity-manifest.tsv"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing starter inputs: {missing}")

    with tempfile.TemporaryDirectory(prefix="magic-tech-starter-") as directory:
        stage = Path(directory)
        minecraft = stage / ".minecraft"
        minecraft.mkdir(parents=True)
        (stage / "instance.cfg").write_text(INSTANCE_CFG, encoding="utf-8", newline="\n")
        shutil.copy2(mmc_pack, stage / "mmc-pack.json")
        shutil.copy2(updater, minecraft / "magic-tech-updater.jar")
        shutil.copy2(bootstrap, minecraft / "packwiz-installer-bootstrap.jar")
        state = minecraft / ".magic-tech"
        state.mkdir()
        shutil.copy2(repo / "integrity-manifest.tsv", state / "integrity-manifest.tsv")

        for relative in local_files:
            copy_file(instance, minecraft, relative)
        for relative in local_trees:
            source_root = safe_resolve(instance, relative)
            if not source_root.is_dir():
                raise FileNotFoundError(f"Missing local starter tree: {relative}")
            for source in sorted(source_root.rglob("*")):
                if source.is_file():
                    copy_file(instance, minecraft, source.relative_to(instance).as_posix())

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage).as_posix())
        temporary.replace(output)


def copy_file(instance: Path, target_root: Path, relative: str) -> None:
    source = safe_resolve(instance, relative)
    if not source.is_file():
        raise FileNotFoundError(f"Missing local starter file: {relative}")
    target = safe_resolve(target_root.resolve(), relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def safe_resolve(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError(f"Unsafe starter path: {relative}")
    return candidate


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build the private PrismLauncher starter instance")
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    parser.add_argument("--output", type=Path, default=repo / "dist/Magic-and-Tech-Starter-0.15.0.zip")
    parser.add_argument("--updater", type=Path, default=repo / "updater/build/magic-tech-updater.jar")
    parser.add_argument("--bootstrap", type=Path, default=repo / "updater/build/packwiz-installer-bootstrap.jar")
    parser.add_argument("--mmc-pack", type=Path, default=DEFAULT_INSTANCE.parent / "mmc-pack.json")
    args = parser.parse_args()
    build_starter(
        args.instance,
        repo,
        args.output,
        DEFAULT_LOCAL_FILES,
        DEFAULT_LOCAL_TREES,
        args.updater,
        args.bootstrap,
        args.mmc_pack,
    )
    print(f"Wrote private starter: {args.output.resolve()}")


if __name__ == "__main__":
    main()
