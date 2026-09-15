package dev.elias.magictech.updater;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

public final class RollbackSnapshot {
    private static final String SNAPSHOT_FILE = "snapshot.tsv";

    private RollbackSnapshot() {
    }

    public static void create(Path instanceRoot, Path backupRoot, IntegrityManifest manifest) throws IOException {
        Path root = instanceRoot.toAbsolutePath().normalize();
        Path backup = backupRoot.toAbsolutePath().normalize();
        requireInside(root, backup);
        deleteTree(backup);
        Files.createDirectories(backup);

        List<String> records = new ArrayList<>();
        records.add("magic-tech-rollback-v1");
        for (IntegrityManifest.Entry entry : manifest.entries()) {
            Path source = safeResolve(root, entry.path());
            if (entry.localOnly()) {
                records.add("keep\t" + entry.path());
                continue;
            }
            if (!Files.isRegularFile(source)) {
                continue;
            }
            Path target = safeResolve(backup, entry.path());
            Files.createDirectories(target.getParent());
            Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES);
            records.add("backup\t" + entry.path());
        }
        Files.write(backup.resolve(SNAPSHOT_FILE), records, StandardCharsets.UTF_8);
    }

    public static void restore(Path instanceRoot, Path backupRoot) throws IOException {
        Path root = instanceRoot.toAbsolutePath().normalize();
        Path backup = backupRoot.toAbsolutePath().normalize();
        requireInside(root, backup);
        List<String> lines = Files.readAllLines(backup.resolve(SNAPSHOT_FILE), StandardCharsets.UTF_8);
        if (lines.isEmpty() || !lines.get(0).equals("magic-tech-rollback-v1")) {
            throw new IOException("Invalid rollback snapshot");
        }

        Set<String> preservedTopLevel = new HashSet<>();
        List<String> restorePaths = new ArrayList<>();
        for (int i = 1; i < lines.size(); i++) {
            String[] fields = lines.get(i).split("\t", -1);
            if (fields.length != 2 || (!fields[0].equals("backup") && !fields[0].equals("keep"))) {
                throw new IOException("Invalid rollback record at line " + (i + 1));
            }
            String path = validatePath(fields[1]);
            if (isExactManagedRootFile(path)) {
                preservedTopLevel.add(path);
            }
            if (fields[0].equals("backup")) {
                restorePaths.add(path);
            }
        }

        removeUnexpectedTopLevel(root, "mods", name -> name.endsWith(".jar"), preservedTopLevel);
        removeUnexpectedTopLevel(root, "tacz", name -> name.endsWith(".zip") || name.endsWith(".zip.disabled"), preservedTopLevel);
        removeUnexpectedTopLevel(root, "resourcepacks", name -> name.endsWith(".zip"), preservedTopLevel);
        removeUnexpectedTopLevel(root, "shaderpacks", name -> name.endsWith(".zip"), preservedTopLevel);

        for (String path : restorePaths) {
            Path source = safeResolve(backup, path);
            Path target = safeResolve(root, path);
            Files.createDirectories(target.getParent());
            Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.COPY_ATTRIBUTES);
        }
    }

    public static void discard(Path instanceRoot, Path backupRoot) throws IOException {
        Path root = instanceRoot.toAbsolutePath().normalize();
        Path backup = backupRoot.toAbsolutePath().normalize();
        requireInside(root, backup);
        deleteTree(backup);
    }

    private static void removeUnexpectedTopLevel(
            Path root,
            String directory,
            java.util.function.Predicate<String> managedName,
            Set<String> preserved
    ) throws IOException {
        Path folder = root.resolve(directory);
        if (!Files.isDirectory(folder)) {
            return;
        }
        try (Stream<Path> stream = Files.list(folder)) {
            for (Path file : stream.filter(Files::isRegularFile).toList()) {
                String relative = directory + "/" + file.getFileName();
                if (managedName.test(file.getFileName().toString()) && !preserved.contains(relative)) {
                    Files.delete(file);
                }
            }
        }
    }


    private static boolean isExactManagedRootFile(String path) {
        int slash = path.indexOf('/');
        return slash > 0 && path.indexOf('/', slash + 1) < 0
                && (path.startsWith("mods/") || path.startsWith("tacz/")
                || path.startsWith("resourcepacks/") || path.startsWith("shaderpacks/"));
    }

    private static Path safeResolve(Path root, String relative) throws IOException {
        String validated = validatePath(relative);
        Path resolved = root.resolve(validated).normalize();
        if (!resolved.startsWith(root)) {
            throw new IOException("Unsafe rollback path: " + relative);
        }
        return resolved;
    }

    private static String validatePath(String value) throws IOException {
        if (value.isBlank() || value.indexOf('\\') >= 0) {
            throw new IOException("Unsafe rollback path: " + value);
        }
        Path path = Path.of(value);
        if (path.isAbsolute() || path.normalize().startsWith("..")
                || !path.normalize().toString().replace('\\', '/').equals(value)) {
            throw new IOException("Unsafe rollback path: " + value);
        }
        return value;
    }

    private static void requireInside(Path root, Path path) throws IOException {
        if (!path.startsWith(root)) {
            throw new IOException("Rollback directory must be inside the instance root");
        }
    }

    private static void deleteTree(Path root) throws IOException {
        if (!Files.exists(root)) {
            return;
        }
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) {
                Files.delete(path);
            }
        }
    }
}
