package dev.elias.magictech.updater;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public record IntegrityManifest(String version, List<Entry> entries) {
    private static final String HEADER = "magic-tech-integrity-v1";

    public IntegrityManifest {
        entries = List.copyOf(entries);
    }

    public static IntegrityManifest parse(List<String> lines) {
        if (lines.isEmpty() || !HEADER.equals(lines.get(0))) {
            throw new IllegalArgumentException("Unsupported integrity manifest header");
        }
        String version = null;
        List<Entry> entries = new ArrayList<>();
        for (int lineNumber = 1; lineNumber < lines.size(); lineNumber++) {
            String line = lines.get(lineNumber);
            if (line.isBlank() || line.startsWith("#")) {
                continue;
            }
            String[] fields = line.split("\\t", -1);
            switch (fields[0]) {
                case "version" -> {
                    requireFieldCount(fields, 2, lineNumber);
                    version = fields[1];
                }
                case "file" -> {
                    requireFieldCount(fields, 5, lineNumber);
                    if (!fields[1].equals("managed") && !fields[1].equals("local")) {
                        throw new IllegalArgumentException("Unknown file origin at line " + (lineNumber + 1));
                    }
                    String hash = fields[2].toLowerCase(Locale.ROOT);
                    if (!hash.matches("[0-9a-f]{64}")) {
                        throw new IllegalArgumentException("Invalid SHA-256 at line " + (lineNumber + 1));
                    }
                    long size;
                    try {
                        size = Long.parseLong(fields[3]);
                    } catch (NumberFormatException exception) {
                        throw new IllegalArgumentException("Invalid file size at line " + (lineNumber + 1), exception);
                    }
                    if (size < 0) {
                        throw new IllegalArgumentException("Invalid file size at line " + (lineNumber + 1));
                    }
                    String path = validateRelativePath(fields[4]);
                    entries.add(new Entry(fields[1].equals("local"), hash, size, path));
                }
                case "exact" -> {
                    // Exact-root declarations are documentation. Exact membership is
                    // derived from file entries so it cannot disagree with hashes.
                    requireFieldCount(fields, 3, lineNumber);
                    validateRelativePath(fields[2]);
                }
                default -> throw new IllegalArgumentException("Unknown manifest record at line " + (lineNumber + 1));
            }
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Integrity manifest has no version");
        }
        return new IntegrityManifest(version, entries);
    }

    private static String validateRelativePath(String value) {
        if (value.isBlank() || value.indexOf('\\') >= 0) {
            throw new IllegalArgumentException("Unsafe manifest path: " + value);
        }
        Path path = Path.of(value);
        if (path.isAbsolute() || path.normalize().startsWith("..") || !path.normalize().toString().replace('\\', '/').equals(value)) {
            throw new IllegalArgumentException("Unsafe manifest path: " + value);
        }
        return value;
    }

    private static void requireFieldCount(String[] fields, int expected, int lineNumber) {
        if (fields.length != expected) {
            throw new IllegalArgumentException("Invalid field count at line " + (lineNumber + 1));
        }
    }

    public record Entry(boolean localOnly, String sha256, long size, String path) {
    }
}
