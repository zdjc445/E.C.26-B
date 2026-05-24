package com.ec26b.shoppingagent.ai;

public record ImagePayload(
        long imageId,
        String imageUrl,
        String contentType,
        byte[] bytes,
        String filename
) {
}
