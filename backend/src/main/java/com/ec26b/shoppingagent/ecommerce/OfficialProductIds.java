package com.ec26b.shoppingagent.ecommerce;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

final class OfficialProductIds {
    private static final long PRODUCT_BASE = 2_000_000_000_000L;
    private static final long PLATFORM_PRODUCT_BASE = 3_000_000_000_000L;
    private static final long RANGE = 900_000_000_000L;

    private OfficialProductIds() {
    }

    static long productId(String platform, String externalId) {
        return stableId(PRODUCT_BASE, platform + ":product:" + externalId);
    }

    static long platformProductId(String platform, String externalId) {
        return stableId(PLATFORM_PRODUCT_BASE, platform + ":platform-product:" + externalId);
    }

    private static long stableId(long base, String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            long raw = ByteBuffer.wrap(bytes, 0, Long.BYTES).getLong() & Long.MAX_VALUE;
            return base + Math.floorMod(raw, RANGE);
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot create stable product id", ex);
        }
    }
}
