package com.ec26b.shoppingagent.config;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.regex.Pattern;

public final class LocalDotEnv {
    private static final String DOTENV_FILE_KEY = "EC26B_DOTENV_FILE";
    private static final Pattern KEY_PATTERN = Pattern.compile("[A-Za-z_][A-Za-z0-9_]*");

    private LocalDotEnv() {
    }

    public static int load() {
        try {
            int loaded = 0;
            for (Path candidate : candidatePaths()) {
                loaded += load(candidate);
            }
            return loaded;
        } catch (IOException ex) {
            throw new IllegalStateException("failed to load local .env file", ex);
        }
    }

    static int load(Path path) throws IOException {
        if (path == null || !Files.isRegularFile(path)) {
            return 0;
        }
        int loaded = 0;
        for (String rawLine : Files.readAllLines(path, StandardCharsets.UTF_8)) {
            DotEnvEntry entry = parse(rawLine);
            if (entry != null && setIfAbsent(entry.name(), entry.value())) {
                loaded++;
            }
        }
        return loaded;
    }

    static DotEnvEntry parse(String rawLine) {
        if (rawLine == null) {
            return null;
        }
        String line = stripBom(rawLine).trim();
        if (line.isBlank() || line.startsWith("#")) {
            return null;
        }
        if (line.startsWith("export ")) {
            line = line.substring(7).trim();
        }
        int separator = line.indexOf('=');
        if (separator <= 0) {
            return null;
        }
        String name = line.substring(0, separator).trim();
        if (!KEY_PATTERN.matcher(name).matches()) {
            return null;
        }
        String value = line.substring(separator + 1).trim();
        if (isQuoted(value)) {
            value = value.substring(1, value.length() - 1);
        }
        return new DotEnvEntry(name, value);
    }

    private static Set<Path> candidatePaths() {
        Set<Path> paths = new LinkedHashSet<>();
        String explicit = firstNonBlank(System.getProperty(DOTENV_FILE_KEY), System.getenv(DOTENV_FILE_KEY));
        if (explicit != null) {
            paths.add(Path.of(explicit).toAbsolutePath().normalize());
            return paths;
        }
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        paths.add(cwd.resolve(".env").normalize());
        Path parent = cwd.getParent();
        if (parent != null) {
            paths.add(parent.resolve(".env").normalize());
        }
        return paths;
    }

    private static boolean setIfAbsent(String name, String value) {
        if (System.getProperty(name) != null || System.getenv(name) != null) {
            return false;
        }
        System.setProperty(name, value);
        return true;
    }

    private static String firstNonBlank(String first, String second) {
        if (first != null && !first.isBlank()) {
            return first;
        }
        return second == null || second.isBlank() ? null : second;
    }

    private static String stripBom(String value) {
        return value.startsWith("\uFEFF") ? value.substring(1) : value;
    }

    private static boolean isQuoted(String value) {
        return value.length() >= 2
                && ((value.startsWith("\"") && value.endsWith("\""))
                || (value.startsWith("'") && value.endsWith("'")));
    }

    record DotEnvEntry(String name, String value) {
    }
}
