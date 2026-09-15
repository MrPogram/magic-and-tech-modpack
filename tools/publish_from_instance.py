#!/usr/bin/env python3
"""Publish all Mod-JAR changes from the owner's Prism instance."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.generate_integrity import DEFAULT_INSTANCE, DEFAULT_LOCAL_FILES

PUBLISHED_BASE_URL = "https://mrpogram.github.io/magic-and-tech-modpack/"
SUPPORTED_HASHES = {"sha1", "sha256", "sha512"}


@dataclass(frozen=True)
class MetadataChange:
    filename: str
    source: Path
    target: Path


@dataclass(frozen=True)
class RemovedMetadata:
    filename: str
    target: Path


@dataclass(frozen=True)
class ModPlan:
    added: list[MetadataChange]
    updated: list[MetadataChange]
    removed: list[RemovedMetadata]
    unresolved: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)


def load_metadata(directory: Path) -> tuple[dict[str, tuple[Path, dict]], list[str]]:
    by_filename: dict[str, tuple[Path, dict]] = {}
    errors: list[str] = []
    if not directory.is_dir():
        return by_filename, errors
    for path in sorted(directory.glob("*.pw.toml")):
        try:
            with path.open("rb") as handle:
                metadata = tomllib.load(handle)
            filename = metadata["filename"]
            if not isinstance(filename, str) or not filename.endswith(".jar"):
                continue
            if filename in by_filename:
                errors.append(f"{filename} (duplicate metadata)")
                continue
            by_filename[filename] = (path, metadata)
        except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
            errors.append(f"{path.name} (invalid metadata: {error})")
    return by_filename, errors


def metadata_matches_file(metadata: dict, jar: Path) -> bool:
    download = metadata.get("download", {})
    algorithm = download.get("hash-format")
    expected = download.get("hash")
    if algorithm not in SUPPORTED_HASHES or not isinstance(expected, str):
        return False
    digest = hashlib.new(algorithm)
    with jar.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected.lower()


def build_mod_plan(repo: Path, instance: Path, local_filenames: set[str]) -> ModPlan:
    validate_instance(instance)
    repo_metadata, repo_errors = load_metadata(repo / "mods")
    instance_metadata, instance_errors = load_metadata(instance / "mods/.index")
    actual = {path.name: path for path in sorted((instance / "mods").glob("*.jar"))}

    added: list[MetadataChange] = []
    updated: list[MetadataChange] = []
    removed: list[RemovedMetadata] = []
    unresolved = repo_errors + instance_errors

    for filename, jar in actual.items():
        if filename in local_filenames:
            continue
        current = repo_metadata.get(filename)
        if current is not None and metadata_matches_file(current[1], jar):
            continue

        candidate = instance_metadata.get(filename)
        if candidate is None:
            suffix = " (metadata hash mismatch)" if current is not None else ""
            unresolved.append(filename + suffix)
            continue
        if not metadata_matches_file(candidate[1], jar):
            unresolved.append(f"{filename} (metadata hash mismatch)")
            continue

        if current is None:
            change = MetadataChange(filename, candidate[0], repo / "mods" / candidate[0].name)
            added.append(change)
        else:
            change = MetadataChange(filename, candidate[0], current[0])
            updated.append(change)

    for filename, (path, _) in repo_metadata.items():
        if filename not in actual and filename not in local_filenames:
            removed.append(RemovedMetadata(filename, path))

    return ModPlan(
        sorted(added, key=lambda item: item.filename),
        sorted(updated, key=lambda item: item.filename),
        sorted(removed, key=lambda item: item.filename),
        sorted(set(unresolved)),
    )


def normalize_metadata_text(content: str) -> str:
    content = re.sub(r"(?m)^side\s*=\s*['\"](?:\s*|server)['\"]\s*$", "side = 'both'", content)
    return re.sub(r"(?m)^url\s*=\s*(['\"])\s*\1\s*\n?", "", content)


def write_normalized_metadata(source: Path, target: Path) -> None:
    content = normalize_metadata_text(source.read_text(encoding="utf-8"))
    target.write_text(content, encoding="utf-8", newline="\n")


def normalize_repository_metadata(repo: Path) -> None:
    for path in sorted((repo / "mods").glob("*.pw.toml")):
        content = path.read_text(encoding="utf-8")
        normalized = normalize_metadata_text(content)
        if normalized != content:
            path.write_text(normalized, encoding="utf-8", newline="\n")


def apply_mod_plan(plan: ModPlan) -> None:
    for change in [*plan.added, *plan.updated]:
        change.target.parent.mkdir(parents=True, exist_ok=True)
        write_normalized_metadata(change.source, change.target)
    for change in plan.removed:
        change.target.unlink()


def print_plan(plan: ModPlan) -> None:
    print(f"Neue Mods:       {len(plan.added)}")
    for change in plan.added:
        print(f"  + {change.filename}")
    print(f"Aktualisierte:   {len(plan.updated)}")
    for change in plan.updated:
        print(f"  ~ {change.filename}")
    print(f"Entfernte Mods:  {len(plan.removed)}")
    for change in plan.removed:
        print(f"  - {change.filename}")
    if plan.unresolved:
        print(f"Nicht auflösbar: {len(plan.unresolved)}")
        for filename in plan.unresolved:
            print(f"  ! {filename}")


def run(command: list[str], repo: Path) -> None:
    print("$ " + " ".join(command))
    subprocess.run(command, cwd=repo, check=True)


def require_clean_repository(repo: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, text=True, capture_output=True
    )
    if result.stdout.strip():
        raise RuntimeError(
            "Das Distributionsrepository enthält bereits Änderungen. "
            "Bitte erst prüfen/abschließen; es wird nichts vermischt.\n" + result.stdout.rstrip()
        )


def validate_instance(instance: Path) -> None:
    mods = instance / "mods"
    metadata = mods / ".index"
    if not mods.is_dir():
        raise ValueError(f"Instanz-Modverzeichnis fehlt: {mods}")
    if not metadata.is_dir():
        raise ValueError(f"Instanz-Metadatenverzeichnis fehlt: {metadata}")


def validate_pack_version(version: str) -> None:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise ValueError(f"Ungültige Packversion: {version}")


def update_pack_version(pack_file: Path, version: str) -> None:
    validate_pack_version(version)
    content = pack_file.read_text(encoding="utf-8")
    updated, count = re.subn(r'(?m)^version = "[^"]+"$', f'version = "{version}"', content, count=1)
    if count != 1:
        raise ValueError("pack.toml enthält keine eindeutige version-Zeile")
    pack_file.write_text(updated, encoding="utf-8", newline="\n")


def packwiz_binary() -> str:
    executable = shutil.which("packwiz")
    if executable is None:
        fallback = Path.home() / ".local/bin/packwiz"
        if fallback.is_file():
            return str(fallback)
        raise RuntimeError("packwiz wurde nicht gefunden")
    return executable


def restore_repository(repo: Path, added_paths: list[Path]) -> None:
    subprocess.run(
        ["git", "restore", "--staged", "--worktree", "--", "."], cwd=repo, check=True
    )
    root = repo.resolve()
    for relative in added_paths:
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise RuntimeError(f"Unsicherer Rollbackpfad: {relative}")
        if target.is_file():
            target.unlink()


def verify_pages(repo: Path) -> None:
    names = ("pack.toml", "index.toml", "integrity-manifest.tsv")
    mismatched: list[str] = list(names)
    for attempt in range(18):
        mismatched = []
        for name in names:
            try:
                with urllib.request.urlopen(PUBLISHED_BASE_URL + name, timeout=30) as response:
                    remote = response.read()
                if remote != (repo / name).read_bytes():
                    mismatched.append(name)
            except OSError:
                mismatched.append(name)
        if not mismatched:
            print("GitHub Pages liefert pack.toml, index.toml und Integritätsmanifest exakt aus.")
            return
        if attempt < 17:
            time.sleep(10)
    raise RuntimeError("GitHub Pages ist nach 3 Minuten noch nicht auf dem neuen Stand: " + ", ".join(mismatched))


def publish(repo: Path, instance: Path, version: str, assume_yes: bool) -> None:
    require_clean_repository(repo)
    validate_pack_version(version)
    validate_instance(instance)
    packwiz = packwiz_binary()
    for required in ("pack.toml", "index.toml", "tools/generate_integrity.py"):
        if not (repo / required).is_file():
            raise RuntimeError(f"Erforderliche Repositorydatei fehlt: {required}")
    local_filenames = {Path(path).name for path in DEFAULT_LOCAL_FILES if Path(path).parent.as_posix() == "mods"}
    plan = build_mod_plan(repo, instance, local_filenames)
    print_plan(plan)
    if plan.unresolved:
        raise RuntimeError(
            "Veröffentlichung abgebrochen: Für jede installierte JAR ist eine passende, "
            "hashrichtige .pw.toml-Quelle erforderlich."
        )
    if not plan.changed:
        print("Keine Modänderungen gegenüber dem Repository gefunden.")
        return

    if not assume_yes:
        answer = input(f"Diesen Modstand als Pack {version} prüfen und veröffentlichen? [y/N] ")
        if answer.strip().lower() not in {"y", "yes", "j", "ja"}:
            print("Abgebrochen; keine Dateien wurden verändert.")
            return

    committed = False
    try:
        apply_mod_plan(plan)
        normalize_repository_metadata(repo)
        update_pack_version(repo / "pack.toml", version)
        run([packwiz, "refresh"], repo)
        run([sys.executable, "tools/generate_integrity.py", "--instance", str(instance)], repo)
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], repo)
        run(["git", "add", "pack.toml", "index.toml", "integrity-manifest.tsv", "mods"], repo)
        run(["git", "diff", "--cached", "--check"], repo)
        run(["git", "commit", "-m", f"Publish pack {version}"], repo)
        committed = True
    except Exception:
        if not committed:
            restore_repository(
                repo,
                [change.target.relative_to(repo) for change in plan.added],
            )
        raise
    run(["git", "push"], repo)
    verify_pages(repo)
    print(f"Pack {version} wurde vollständig veröffentlicht.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alle hinzugefügten, aktualisierten und entfernten Mod-JARs aus der Prism-Instanz veröffentlichen"
    )
    parser.add_argument("version", help="Neue Packversion, z. B. 0.15.1")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    parser.add_argument("--dry-run", action="store_true", help="Nur Änderungen anzeigen")
    parser.add_argument("--yes", action="store_true", help="Rückfrage überspringen")
    args = parser.parse_args()

    repo = args.repo.resolve()
    instance = args.instance.resolve()
    local_filenames = {Path(path).name for path in DEFAULT_LOCAL_FILES if Path(path).parent.as_posix() == "mods"}
    try:
        if args.dry_run:
            plan = build_mod_plan(repo, instance, local_filenames)
            print_plan(plan)
            raise SystemExit(2 if plan.unresolved else 0)
        publish(repo, instance, args.version, args.yes)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"FEHLER: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
