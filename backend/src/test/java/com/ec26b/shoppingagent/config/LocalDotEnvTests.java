package com.ec26b.shoppingagent.config;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class LocalDotEnvTests {
    @TempDir
    Path tempDir;

    @Test
    void loadsDotEnvValuesWithoutOverridingExistingRuntimeValues() throws Exception {
        Path envFile = tempDir.resolve(".env");
        Files.writeString(envFile, """
                # comment
                export EC26B_TEST_DOTENV_ONE=alpha
                EC26B_TEST_DOTENV_QUOTED="two words"
                EC26B_TEST_DOTENV_WITH_EQUALS=a=b=c
                EC26B_TEST_DOTENV_EXISTING=file-value
                BAD-NAME=ignored
                """);

        System.setProperty("EC26B_TEST_DOTENV_EXISTING", "runtime-value");
        try {
            int loaded = LocalDotEnv.load(envFile);

            assertThat(loaded).isEqualTo(3);
            assertThat(System.getProperty("EC26B_TEST_DOTENV_ONE")).isEqualTo("alpha");
            assertThat(System.getProperty("EC26B_TEST_DOTENV_QUOTED")).isEqualTo("two words");
            assertThat(System.getProperty("EC26B_TEST_DOTENV_WITH_EQUALS")).isEqualTo("a=b=c");
            assertThat(System.getProperty("EC26B_TEST_DOTENV_EXISTING")).isEqualTo("runtime-value");
            assertThat(System.getProperty("BAD-NAME")).isNull();
        } finally {
            System.clearProperty("EC26B_TEST_DOTENV_ONE");
            System.clearProperty("EC26B_TEST_DOTENV_QUOTED");
            System.clearProperty("EC26B_TEST_DOTENV_WITH_EQUALS");
            System.clearProperty("EC26B_TEST_DOTENV_EXISTING");
        }
    }

    @Test
    void parsesSupportedDotEnvLines() {
        assertThat(LocalDotEnv.parse("export EC26B_TEST_KEY='secret value'"))
                .isEqualTo(new LocalDotEnv.DotEnvEntry("EC26B_TEST_KEY", "secret value"));
        assertThat(LocalDotEnv.parse("  # comment")).isNull();
        assertThat(LocalDotEnv.parse("not a pair")).isNull();
        assertThat(LocalDotEnv.parse("BAD-NAME=value")).isNull();
    }
}
