#!/usr/bin/env python3
import argparse
import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INSTANCE = Path("/home/elias/snap/prismlauncher-alpo/common/instances/magic_and_tech/minecraft")
DEFAULT_LOCAL_FILES = [
    "mods/aether_ii-1.20.1-1.0.13-forge.jar",
    "tacz/[Tacz1.1.5+]TRIS-dyna GunsPack ver1.1.5.zip.zip",
]
DEFAULT_LOCAL_TREES = ["tacz/immersive_ballistic"]
RAW_ROOTS = ("config", "defaultconfigs", "figura")
EXACT_ROOTS = {
    "mods": lambda name: name.endswith(".jar"),
    "tacz": lambda name: name.endswith(".zip") or name.endswith(".zip.disabled"),
    "resourcepacks": lambda name: name.endswith(".zip"),
    "shaderpacks": lambda name: name.endswith(".zip"),
}


@dataclass(frozen=True)
class Entry:
    origin: str
    path: str
    size: int
    sha256: str


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_entry(entries: dict[str, Entry], instance: Path, relative: str, origin: str) -> None:
    normalized = Path(relative)
    if normalized.is_absolute() or ".." in normalized.parts or "\\" in relative:
        raise ValueError(f"Unsafe manifest path: {relative}")
    canonical = normalized.as_posix()
    if canonical in entries:
        raise ValueError(f"Duplicate output path: {canonical}")
    source = instance / normalized
    if not source.is_file():
        raise ValueError(f"Missing instance file: {canonical}")
    entries[canonical] = Entry(origin, canonical, source.stat().st_size, file_hash(source))


def build_manifest(repo: Path, instance: Path, local_files: list[str], local_trees: list[str]) -> str:
    repo = repo.resolve()
    instance = instance.resolve()
    with (repo / "pack.toml").open("rb") as handle:
        pack_version = str(tomllib.load(handle)["version"])

    entries: dict[str, Entry] = {}
    for metafile in sorted(repo.rglob("*.pw.toml")):
        if any(part in {".git", "updater", "starter", "dist"} for part in metafile.parts):
            continue
        with metafile.open("rb") as handle:
            metadata = tomllib.load(handle)
        output = metafile.parent.relative_to(repo) / metadata["filename"]
        add_entry(entries, instance, output.as_posix(), "managed")

    for root_name in RAW_ROOTS:
        root = repo / root_name
        if not root.is_dir():
            continue
        for source in sorted(root.rglob("*")):
            if not source.is_file() or source.name.endswith(".pw.toml"):
                continue
            relative = source.relative_to(repo).as_posix()
            if relative in entries:
                raise ValueError(f"Duplicate output path: {relative}")
            entries[relative] = Entry("managed", relative, source.stat().st_size, file_hash(source))

    for relative in local_files:
        add_entry(entries, instance, relative, "local")
    for tree_name in local_trees:
        tree = instance / tree_name
        if not tree.is_dir():
            raise ValueError(f"Missing local tree: {tree_name}")
        for source in sorted(tree.rglob("*")):
            if source.is_file():
                add_entry(entries, instance, source.relative_to(instance).as_posix(), "local")

    for root_name, accepted in EXACT_ROOTS.items():
        actual_root = instance / root_name
        actual = {
            f"{root_name}/{path.name}"
            for path in actual_root.iterdir()
            if path.is_file() and accepted(path.name)
        } if actual_root.is_dir() else set()
        expected = {
            path for path in entries
            if Path(path).parent.as_posix() == root_name and accepted(Path(path).name)
        }
        if actual != expected:
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            raise ValueError(
                f"Unexpected or missing files in {root_name}: missing={missing}, unexpected={unexpected}"
            )

    lines = ["magic-tech-integrity-v1", f"version\t{pack_version}"]
    for entry in sorted(entries.values(), key=lambda item: item.path):
        lines.append(f"file\t{entry.origin}\t{entry.sha256}\t{entry.size}\t{entry.path}")
    for root_name, accepted in EXACT_ROOTS.items():
        for path in sorted(p for p in entries if Path(p).parent.as_posix() == root_name and accepted(Path(p).name)):
            lines.append(f"exact\t{root_name}\t{path}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the fail-closed Magic and Tech integrity manifest")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.repo / "integrity-manifest.tsv"
    manifest = build_manifest(args.repo, args.instance, DEFAULT_LOCAL_FILES, DEFAULT_LOCAL_TREES)
    output.write_text(manifest, encoding="utf-8", newline="\n")
    print(f"Wrote {output} with {manifest.count(chr(10)) - 2} records")


if __name__ == "__main__":
    main()
