package dev.elias.magictech.updater;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Set;
import java.util.function.Predicate;
import java.util.stream.Stream;

public final class IntegrityVerifier {
    private IntegrityVerifier() {
    }

    public static void verify(Path instanceRoot, IntegrityManifest manifest, boolean localOnly) throws IOException {
        Path normalizedRoot = instanceRoot.toAbsolutePath().normalize();
        for (IntegrityManifest.Entry entry : manifest.entries()) {
            if (localOnly && !entry.localOnly()) {
                continue;
            }
            verifyEntry(normalizedRoot, entry);
        }
        if (!localOnly) {
            verifyExactTopLevelFiles(normalizedRoot, manifest, "mods", name -> name.endsWith(".jar"));
            verifyExactTopLevelFiles(normalizedRoot, manifest, "tacz", name -> name.endsWith(".zip") || name.endsWith(".zip.disabled"));
            verifyExactTopLevelFiles(normalizedRoot, manifest, "resourcepacks", name -> name.endsWith(".zip"));
            verifyExactTopLevelFiles(normalizedRoot, manifest, "shaderpacks", name -> name.endsWith(".zip"));
        }
    }

    private static void verifyEntry(Path root, IntegrityManifest.Entry entry) throws IOException {
        Path file = root.resolve(entry.path()).normalize();
        if (!file.startsWith(root)) {
            throw new IOException("Unsafe manifest path: " + entry.path());
        }
        if (!Files.isRegularFile(file)) {
            throw new IOException("Missing required file: " + entry.path());
        }
        Path realRoot = root.toRealPath();
        if (!file.toRealPath().startsWith(realRoot)) {
            throw new IOException("Required file escapes instance root: " + entry.path());
        }
        long actualSize = Files.size(file);
        if (actualSize != entry.size()) {
            throw new IOException("File size mismatch for " + entry.path() + ": expected " + entry.size() + ", got " + actualSize);
        }
        String actualHash = sha256(file);
        if (!actualHash.equals(entry.sha256())) {
            throw new IOException("SHA-256 mismatch for " + entry.path());
        }
    }

    private static void verifyExactTopLevelFiles(
            Path root,
            IntegrityManifest manifest,
            String directory,
            Predicate<String> managedName
    ) throws IOException {
        Set<String> expected = new HashSet<>();
        String prefix = directory + "/";
        for (IntegrityManifest.Entry entry : manifest.entries()) {
            if (entry.path().startsWith(prefix) && entry.path().indexOf('/', prefix.length()) < 0 && managedName.test(entry.path())) {
                expected.add(entry.path());
            }
        }
        Path folder = root.resolve(directory);
        if (!Files.isDirectory(folder)) {
            if (!expected.isEmpty()) {
                throw new IOException("Missing managed directory: " + directory);
            }
            return;
        }
        try (Stream<Path> files = Files.list(folder)) {
            for (Path file : files.filter(Files::isRegularFile).toList()) {
                String relative = directory + "/" + file.getFileName();
                if (managedName.test(relative) && !expected.contains(relative)) {
                    throw new IOException("Unexpected managed-root file: " + relative);
                }
            }
        }
    }

    private static String sha256(Path file) throws IOException {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
        byte[] buffer = new byte[1024 * 1024];
        try (InputStream input = Files.newInputStream(file)) {
            int count;
            while ((count = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, count);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
