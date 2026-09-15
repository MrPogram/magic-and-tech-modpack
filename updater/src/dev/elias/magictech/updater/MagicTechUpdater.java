package dev.elias.magictech.updater;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;

public final class MagicTechUpdater {
    private static final String DEFAULT_BASE_URL = "https://mrpogram.github.io/magic-and-tech-modpack/";

    private MagicTechUpdater() {
    }

    public static void main(String[] args) {
        try {
            run(args);
        } catch (Exception exception) {
            System.err.println("[Magic and Tech Updater] UPDATE ABORTED: " + exception.getMessage());
            exception.printStackTrace(System.err);
            System.exit(1);
        }
    }

    static void run(String[] args) throws Exception {
        Path root = Path.of(argument(args, 0, ".")).toAbsolutePath().normalize();
        String baseUrl = withTrailingSlash(argument(args, 1, DEFAULT_BASE_URL));
        Path bootstrap = root.resolve(argument(args, 2, "packwiz-installer-bootstrap.jar")).normalize();
        if (!bootstrap.startsWith(root) || !Files.isRegularFile(bootstrap)) {
            throw new IOException("Missing Packwiz bootstrap: " + bootstrap);
        }

        byte[] remoteBytes = download(baseUrl + "integrity-manifest.tsv");
        List<String> remoteLines = Arrays.asList(new String(remoteBytes, StandardCharsets.UTF_8).split("\\R"));
        IntegrityManifest remoteManifest = IntegrityManifest.parse(remoteLines);
        System.out.println("[Magic and Tech Updater] Checking local-only files for pack " + remoteManifest.version());
        IntegrityVerifier.verify(root, remoteManifest, true);

        Path stateRoot = root.resolve(".magic-tech");
        Path localManifestFile = stateRoot.resolve("integrity-manifest.tsv");
        Path rollbackRoot = stateRoot.resolve("rollback");
        boolean rollbackCreated = false;
        if (Files.isRegularFile(localManifestFile)) {
            byte[] localBytes = Files.readAllBytes(localManifestFile);
            if (!Arrays.equals(localBytes, remoteBytes)) {
                IntegrityManifest previous = IntegrityManifest.parse(Files.readAllLines(localManifestFile, StandardCharsets.UTF_8));
                System.out.println("[Magic and Tech Updater] Creating rollback snapshot for " + previous.version());
                RollbackSnapshot.create(root, rollbackRoot, previous);
                rollbackCreated = true;
            } else {
                prepareSameVersionRepair(root, remoteManifest);
            }
        } else {
            Files.createDirectories(stateRoot);
        }

        try {
            int exitCode = runPackwiz(root, bootstrap, baseUrl + "pack.toml");
            if (exitCode != 0) {
                throw new IOException("Packwiz exited with code " + exitCode);
            }
            System.out.println("[Magic and Tech Updater] Verifying complete pack " + remoteManifest.version());
            IntegrityVerifier.verify(root, remoteManifest, false);
            writeAtomically(localManifestFile, remoteBytes);
            if (rollbackCreated) {
                RollbackSnapshot.discard(root, rollbackRoot);
            }
            System.out.println("[Magic and Tech Updater] VERIFIED — starting Minecraft");
        } catch (Exception updateFailure) {
            if (rollbackCreated) {
                try {
                    System.err.println("[Magic and Tech Updater] Update failed; restoring previous pack");
                    RollbackSnapshot.restore(root, rollbackRoot);
                } catch (Exception rollbackFailure) {
                    updateFailure.addSuppressed(rollbackFailure);
                }
            }
            throw updateFailure;
        }
    }

    static boolean prepareSameVersionRepair(Path root, IntegrityManifest manifest) throws IOException {
        try {
            IntegrityVerifier.verify(root, manifest, false);
            return false;
        } catch (IOException integrityFailure) {
            System.err.println("[Magic and Tech Updater] Current pack is damaged; forcing a complete Packwiz repair: "
                    + integrityFailure.getMessage());
            Files.deleteIfExists(root.resolve("packwiz.json"));
            return true;
        }
    }

    private static int runPackwiz(Path root, Path bootstrap, String packUrl) throws IOException, InterruptedException {
        String executable = System.getProperty("os.name").toLowerCase().contains("win") ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"), "bin", executable);
        Process process = new ProcessBuilder(packwizCommand(java, bootstrap, packUrl))
                .directory(root.toFile()).inheritIO().start();
        return process.waitFor();
    }

    static List<String> packwizCommand(Path java, Path bootstrap, String packUrl) {
        return List.of(
                java.toString(),
                "-jar",
                bootstrap.toString(),
                "-g",
                packUrl
        );
    }

    private static byte[] download(String url) throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(60))
                .header("User-Agent", "Magic-and-Tech-Updater/1")
                .GET()
                .build();
        HttpResponse<byte[]> response = client.send(request, HttpResponse.BodyHandlers.ofByteArray());
        if (response.statusCode() != 200) {
            throw new IOException("Failed to download " + url + " (HTTP " + response.statusCode() + ")");
        }
        return response.body();
    }

    private static void writeAtomically(Path target, byte[] bytes) throws IOException {
        Files.createDirectories(target.getParent());
        Path temporary = target.resolveSibling(target.getFileName() + ".tmp");
        Files.write(temporary, bytes);
        try {
            Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException unsupportedAtomicMove) {
            Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static String argument(String[] args, int index, String defaultValue) {
        return args.length > index && !args[index].isBlank() ? args[index] : defaultValue;
    }

    private static String withTrailingSlash(String value) {
        return value.endsWith("/") ? value : value + "/";
    }
}
