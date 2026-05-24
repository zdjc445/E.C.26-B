package com.ec26b.shoppingagent.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.nio.file.Path;

@Configuration
public class WebConfig implements WebMvcConfigurer {
    private final String uploadDir;

    public WebConfig(@Value("${app.upload-dir}") String uploadDir) {
        this.uploadDir = uploadDir;
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        Path path = resolveUploadsPath();
        registry.addResourceHandler("/uploads/**")
                .addResourceLocations(path.toUri().toString());
    }

    private Path resolveUploadsPath() {
        Path configured = Path.of(uploadDir);
        if (configured.isAbsolute()) {
            return configured;
        }
        Path cwd = Path.of("").toAbsolutePath();
        if (cwd.resolve(configured).toFile().exists()) {
            return cwd.resolve(configured);
        }
        return cwd.resolve("..").resolve(configured).normalize();
    }
}
