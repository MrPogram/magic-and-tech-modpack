package dev.elias.magictech.updater;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;

public final class IntegrityVerifierTest {
    public static void main(String[] args) throws Exception {
        verifiesExpectedFile();
        rejectsMissingFile();
        rejectsWrongHash();
        rejectsUnexpectedTopLevelJar();
        rejectsPathTraversal();
        restoresManagedFilesWithoutTouchingLocalFiles();
        packwizRunsWithoutInteractiveGui();
        corruptedCurrentPackForcesPackwizRepair();
        System.out.println("IntegrityVerifierTest: PASS");
    }

    private static void verifiesExpectedFile() throws Exception {
        Path root = Files.createTempDirectory("integrity-ok");
        Files.createDirectories(root.resolve("mods"));
        Path file = root.resolve("mods/example.jar");
        Files.writeString(file, "expected", StandardCharsets.UTF_8);
        IntegrityManifest manifest = IntegrityManifest.parse(List.of(
                "magic-tech-integrity-v1",
                "version\t0.15.0",
                "file\tmanaged\t" + sha256(file) + "\t8\tmods/example.jar",
                "exact\tmods-jars\tmods/example.jar"
        ));
        IntegrityVerifier.verify(root, manifest, false);
    }

    private static void rejectsMissingFile() throws Exception {
        Path root = Files.createTempDirectory("integrity-missing");
        IntegrityManifest manifest = IntegrityManifest.parse(List.of(
                "magic-tech-integrity-v1",
                "version\t0.15.0",
                "file\tlocal\t" + "0".repeat(64) + "\t1\tmods/missing.jar"
        ));
        expectFailure(() -> IntegrityVerifier.verify(root, manifest, true), "Missing required file");
    }

    private static void rejectsWrongHash() throws Exception {
        Path root = Files.createTempDirectory("integrity-hash");
        Files.createDirectories(root.resolve("mods"));
        Files.writeString(root.resolve("mods/example.jar"), "wrong", StandardCharsets.UTF_8);
        IntegrityManifest manifest = IntegrityManifest.parse(List.of(
                "magic-tech-integrity-v1",
                "version\t0.15.0",
                "file\tmanaged\t" + "0".repeat(64) + "\t5\tmods/example.jar"
        ));
        expectFailure(() -> IntegrityVerifier.verify(root, manifest, false), "SHA-256 mismatch");
    }

    private static void rejectsUnexpectedTopLevelJar() throws Exception {
        Path root = Files.createTempDirectory("integrity-extra");
        Files.createDirectories(root.resolve("mods"));
        Files.writeString(root.resolve("mods/unmanaged.jar"), "extra", StandardCharsets.UTF_8);
        IntegrityManifest manifest = IntegrityManifest.parse(List.of(
                "magic-tech-integrity-v1",
                "version\t0.15.0"
        ));
        expectFailure(() -> IntegrityVerifier.verify(root, manifest, false), "Unexpected managed-root file");
    }

    private static void rejectsPathTraversal() {
        expectFailure(() -> IntegrityManifest.parse(List.of(
                "magic-tech-integrity-v1",
                "version\t0.15.0",
                "file\tmanaged\t" + "0".repeat(64) + "\t1\t../escape.jar"
        )), "Unsafe manifest path");
    }

    private static void restoresManagedFilesWithoutTouchingLocalFiles() throws Exception {
        Path root = Files.createTempDirectory("integrity-rollback");
        Path managed = root.resolve("mods/managed.jar");
        Path config = root.resolve("config/game.toml");
        Path local = root.resolve("mods/local.jar");
        Files.createDirectories(managed.getParent());
        Files.createDirectories(config.getParent());
        Files.writeString(managed, "managed-before", StandardCharsets.UTF_8);
        Files.writeString(config, "config-before", StandardCharsets.UTF_8);
        Files.writeString(local, "local-before", StandardCharsets.UTF_8);
        IntegrityManifest manifest = IntegrityManifest.parse(List.of(
                "magic-tech-integrity-v1",
                "version\t0.15.0",
                "file\tmanaged\t" + sha256(managed) + "\t14\tmods/managed.jar",
                "file\tmanaged\t" + sha256(config) + "\t13\tconfig/game.toml",
                "file\tlocal\t" + sha256(local) + "\t12\tmods/local.jar"
        ));
        Path backup = root.resolve(".magic-tech/rollback");
        RollbackSnapshot.create(root, backup, manifest);

        Files.writeString(managed, "broken", StandardCharsets.UTF_8);
        Files.delete(config);
        Files.writeString(local, "local-after", StandardCharsets.UTF_8);
        RollbackSnapshot.restore(root, backup);

        assertEquals("managed-before", Files.readString(managed), "managed mod rollback");
        assertEquals("config-before", Files.readString(config), "config rollback");
        assertEquals("local-after", Files.readString(local), "local-only file must remain untouched");
    }

    private static void packwizRunsWithoutInteractiveGui() {
        List<String> command = MagicTechUpdater.packwizCommand(
                Path.of("java"), Path.of("bootstrap.jar"), "https://example.invalid/pack.toml");
        if (!command.equals(List.of(
                "java", "-jar", "bootstrap.jar", "-g", "https://example.invalid/pack.toml"))) {
            throw new AssertionError("Packwiz must run headlessly: " + command);
        }
    }

    private static void corruptedCurrentPackForcesPackwizRepair() throws Exception {
        Path root = Files.createTempDirectory("integrity-repair");
        Path managed = root.resolve("config/managed.txt");
        Files.createDirectories(managed.getParent());
        Files.writeString(managed, "expected", StandardCharsets.UTF_8);
        IntegrityManifest manifest = IntegrityManifest.parse(List.of(
                "magic-tech-integrity-v1",
                "version\t0.15.0",
                "file\tmanaged\t" + sha256(managed) + "\t8\tconfig/managed.txt"
        ));
        Files.writeString(managed, "corrupt", StandardCharsets.UTF_8);
        Path packwizState = root.resolve("packwiz.json");
        Files.writeString(packwizState, "{}", StandardCharsets.UTF_8);

        boolean repairRequired = MagicTechUpdater.prepareSameVersionRepair(root, manifest);

        if (!repairRequired || Files.exists(packwizState)) {
            throw new AssertionError("Corrupt current pack must clear packwiz state for a full repair");
        }
    }

    private static String sha256(Path path) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    }

    private static void expectFailure(ThrowingRunnable action, String expected) {
        try {
            action.run();
            throw new AssertionError("Expected failure containing: " + expected);
        } catch (Exception exception) {
            if (!exception.getMessage().contains(expected)) {
                throw new AssertionError("Expected '" + expected + "' but got: " + exception.getMessage(), exception);
            }
        }
    }

    private static void assertEquals(String expected, String actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected '" + expected + "' but got '" + actual + "'");
        }
    }

    @FunctionalInterface
    private interface ThrowingRunnable {
        void run() throws Exception;
    }
}
