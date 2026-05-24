package com.ec26b.shoppingagent.ecommerce;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.TreeMap;

final class EcommerceSigning {
    private EcommerceSigning() {
    }

    static String md5SignWithSecretWrap(Map<String, String> params, String secret) {
        TreeMap<String, String> sorted = new TreeMap<>(params);
        StringBuilder payload = new StringBuilder(secret);
        sorted.forEach((key, value) -> {
            if (!"sign".equals(key) && value != null) {
                payload.append(key).append(value);
            }
        });
        payload.append(secret);
        return md5Upper(payload.toString());
    }

    static String md5Upper(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("MD5");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(bytes.length * 2);
            for (byte item : bytes) {
                hex.append(String.format("%02X", item));
            }
            return hex.toString();
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot create API signature", ex);
        }
    }
}
