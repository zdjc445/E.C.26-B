package com.ec26b.shoppingagent.ai;

public record ImagePayload(
        String imageId,
        String contentType,
        byte[] bytes,
        String filename
) {}
