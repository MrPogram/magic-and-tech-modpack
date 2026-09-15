# Releasing a Magic and Tech pack update

## Invariants

- Stop all Minecraft/Forge JVMs before replacing JARs.
- Keep `saves/`, `options.txt`, accounts, logs, caches, backups, and credentials outside this repository.
- Never publish a third-party binary unless its original platform metadata or redistribution permission is verified.
- A release is complete only after a clean starter install, SHA-256 verification, removal test, rollback test, and real Forge launch.

## Normal mod release: one command

Add, update, and remove mods in the owner PrismLauncher instance as usual. Then run:

```bash
./tools/publish_from_instance.py <new-pack-version>
```

Example:

```bash
./tools/publish_from_instance.py 0.15.1
```

The command compares every active top-level Mod JAR with this repository. It imports all matching `.pw.toml` metadata from the instance—including separately installed dependencies—removes metadata for deleted JARs, checks source hashes, updates the pack version and integrity manifest, runs the Python regression suite, commits, pushes, and waits until GitHub Pages serves byte-identical manifests.

Before changing or publishing anything it prints the complete add/update/remove plan and asks for confirmation. `--dry-run` only reports the plan. If any JAR lacks hash-correct source metadata, publication fails closed and lists every unresolved file; it never publishes a partial pack.

The repository must be clean before publication so unrelated work cannot be included accidentally. The command handles Mod JAR changes only; reviewed config, quest, Figura, TaCZ, resource-pack, and shader-pack changes remain explicit release inputs.

## Manual fallback for platform-hosted content

Only use these commands when the automatic scan reports an unresolved Mod JAR:

```bash
packwiz modrinth add <project-or-url>
packwiz curseforge add <project-or-url>
packwiz remove <metadata-name>
packwiz refresh
```

TaCZ customization metadata belongs under `tacz/` by using `--meta-folder tacz`.

## Updating pack-owned files

1. Build and test the custom mod in its source repository.
2. Increment the pack version in `pack.toml`.
3. Update custom `.pw.toml` filenames, release URLs, and hashes.
4. Copy reviewed pack-owned overrides into this repository. Do not copy the complete runtime `config/` tree.
5. Update the explicit local-only allowlist in `tools/generate_integrity.py` only when no lawful stable download URL exists.

## Verification and build

```bash
python3 -m unittest discover -s tests -v
packwiz refresh
python3 tools/generate_integrity.py

JDK=/home/elias/snap/prismlauncher-alpo/common/java/java-runtime-gamma/bin
rm -rf updater/build/classes updater/build/test-classes
mkdir -p updater/build/classes updater/build/test-classes
"$JDK/javac" --release 17 -d updater/build/classes $(find updater/src -name '*.java' -print)
"$JDK/javac" --release 17 -cp updater/build/classes -d updater/build/test-classes $(find updater/test -name '*.java' -print)
"$JDK/java" -cp updater/build/classes:updater/build/test-classes dev.elias.magictech.updater.IntegrityVerifierTest
printf 'Main-Class: dev.elias.magictech.updater.MagicTechUpdater\n' > updater/build/MANIFEST.MF
"$JDK/jar" --create --file updater/build/magic-tech-updater.jar --manifest updater/build/MANIFEST.MF -C updater/build/classes .

python3 tools/build_starter.py
python3 -m zipfile -t dist/Magic-and-Tech-Starter-0.15.0.zip
```

The generator aborts if a JAR/ZIP is missing, unexpected, duplicated, or different from its declared source.

## Publish order

1. Commit and push the metadata/configuration/integrity changes.
2. Upload only pack-owned custom JARs to the matching GitHub release tag.
3. Wait for GitHub Pages to serve the new commit.
4. Download `pack.toml`, `index.toml`, `integrity-manifest.tsv`, and custom release assets again; compare their hashes with the local release inputs.
5. Extract the private starter into a disposable directory and run its updater.
6. Corrupt one managed test file and confirm launch refusal and repair.
7. Test a pack version that removes one tracked file; confirm Packwiz removes it while a sentinel world/options file remains unchanged.
8. Launch the disposable Prism instance and verify Forge discovers the exact custom mod versions without new pack-related errors.
9. Only then distribute the private starter ZIP to players.

## Rollback

During a version change the updater copies the previous managed files into `.minecraft/.magic-tech/rollback/`. If Packwiz or final integrity verification fails, those files are restored and the updater exits non-zero. The snapshot is deleted only after complete verification succeeds.

Git history and release tags retain previously published manifests. To perform an owner-side release rollback, republish the previous `pack.toml`, `index.toml`, metadata, and `integrity-manifest.tsv` as a new corrective commit; clients then receive that declared state on their next launch.
