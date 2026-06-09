package com.ec26b.shoppingagent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

@SpringBootApplication
public class ShoppingAgentApplication {

    public static void main(String[] args) {
        loadDotEnv();
        SpringApplication.run(ShoppingAgentApplication.class, args);
    }

    /**
     * Load key=value pairs from a .env file and set them as system properties
     * so that Spring Boot {@code ${ENV:default}} placeholders can pick them up.
     */
    private static void loadDotEnv() {
        // Look for .env in the project root (one level above the backend directory)
        Path envFile = Paths.get(".env");
        if (!Files.isRegularFile(envFile)) {
            // Fallback: look relative to backend/ working directory
            envFile = Paths.get("../.env");
        }
        if (!Files.isRegularFile(envFile)) {
            System.out.println("[dotenv] No .env file found — using system env only.");
            return;
        }
        try {
            for (String line : Files.readAllLines(envFile)) {
                line = line.strip();
                if (line.isEmpty() || line.startsWith("#")) continue;
                int eq = line.indexOf('=');
                if (eq <= 0) continue;
                String key = line.substring(0, eq).strip();
                String value = line.substring(eq + 1).strip();
                // Only set if not already present in system environment
                if (System.getProperty(key) == null) {
                    System.setProperty(key, value);
                }
            }
            System.out.println("[dotenv] Loaded " + envFile.toAbsolutePath().normalize());
        } catch (IOException e) {
            System.out.println("[dotenv] Failed to read " + envFile + ": " + e.getMessage());
        }
    }
}
