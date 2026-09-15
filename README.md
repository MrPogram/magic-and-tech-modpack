# Magic and Tech Modpack Distribution

This repository is the public, hash-addressed distribution source for the **Magic and Tech** Forge 1.20.1 modpack.

## Player installation

Players do not clone this repository and do not manage Packwiz manually.

1. Obtain `Magic-and-Tech-Starter-0.15.0.zip` privately from the pack owner.
2. In PrismLauncher, choose **Add Instance → Import from zip**.
3. Start the imported **Magic and Tech** instance.
4. The pre-launch updater downloads the published pack, verifies every expected file with SHA-256, and starts Minecraft only after verification succeeds.

Future updates run automatically before every Minecraft launch. e4mc is used only for the later game connection; pack synchronization does not depend on e4mc.

## Fail-closed behavior

The custom Java bootstrap:

- downloads `integrity-manifest.tsv` over HTTPS;
- verifies local-only prerequisites before changing the installation;
- runs the official Packwiz installer;
- verifies every managed and local-only file after installation;
- rejects unexpected top-level mod JARs and pack ZIPs;
- creates a rollback snapshot before version changes;
- restores the previous managed state when an update fails;
- exits non-zero so PrismLauncher does not start Forge with a mixed pack state.

## Privacy and redistribution boundary

The public repository contains Packwiz metadata, pack-owned configuration/assets, updater source, and hashes. It intentionally excludes worlds, player options, accounts, server lists, logs, screenshots, caches, backups, voice-chat identity caches, and local web-configuration credentials.

Some required third-party files have no verified public redistribution URL. They are present only in the privately shared starter archive and are represented publicly by filename, size, and SHA-256. They are never committed or uploaded as GitHub release assets.

## Published endpoints

- Pack manifest: `https://mrpogram.github.io/magic-and-tech-modpack/pack.toml`
- Integrity manifest: `https://mrpogram.github.io/magic-and-tech-modpack/integrity-manifest.tsv`

See [RELEASING.md](RELEASING.md) for the maintainer workflow.

For ordinary Mod additions, updates, dependency changes, and removals, the owner publishes the complete current instance delta with one command:

```bash
./tools/publish_from_instance.py <new-pack-version>
```

Players still only start Minecraft; this command is exclusively for the pack owner.
