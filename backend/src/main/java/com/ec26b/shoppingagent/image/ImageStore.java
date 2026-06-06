package com.ec26b.shoppingagent.image;

import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class ImageStore {

    private final Map<String, ImageMetadata> store = new ConcurrentHashMap<>();

    public ImageMetadata save(String imageId, String storedFileName, String originalFileName,
                              String contentType, long size) {
        var meta = new ImageMetadata(imageId, storedFileName, originalFileName,
                contentType, size, OffsetDateTime.now());
        store.put(imageId, meta);
        return meta;
    }

    public Optional<ImageMetadata> findById(String imageId) {
        return Optional.ofNullable(store.get(imageId));
    }

    public record ImageMetadata(
            String imageId,
            String storedFileName,
            String originalFileName,
            String contentType,
            long size,
            OffsetDateTime createdAt
    ) {}
}
