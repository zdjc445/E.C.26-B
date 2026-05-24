package com.ec26b.shoppingagent.security;

import com.ec26b.shoppingagent.api.ApiException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;

@Service
public class JwtService {
    private final byte[] secret;
    private final long accessTokenSeconds;

    public JwtService(
            @Value("${app.jwt.secret}") String secret,
            @Value("${app.jwt.access-token-seconds}") long accessTokenSeconds
    ) {
        this.secret = secret.getBytes(StandardCharsets.UTF_8);
        this.accessTokenSeconds = accessTokenSeconds;
    }

    public long accessTokenSeconds() {
        return accessTokenSeconds;
    }

    public String createAccessToken(long userId) {
        long expiresAt = Instant.now().plusSeconds(accessTokenSeconds).getEpochSecond();
        String payload = encode(userId + ":" + expiresAt);
        String signature = sign(payload);
        return payload + "." + signature;
    }

    public long requireUserId(String token) {
        try {
            String[] parts = token.split("\\.");
            if (parts.length != 2 || !constantTimeEquals(sign(parts[0]), parts[1])) {
                throw ApiException.unauthorized("invalid access token");
            }
            String[] payload = decode(parts[0]).split(":");
            long userId = Long.parseLong(payload[0]);
            long expiresAt = Long.parseLong(payload[1]);
            if (Instant.now().getEpochSecond() > expiresAt) {
                throw new ApiException(40102, "access token expired", org.springframework.http.HttpStatus.UNAUTHORIZED);
            }
            return userId;
        } catch (ApiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new ApiException(40102, "invalid access token", org.springframework.http.HttpStatus.UNAUTHORIZED);
        }
    }

    private String encode(String value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    private String decode(String value) {
        return new String(Base64.getUrlDecoder().decode(value), StandardCharsets.UTF_8);
    }

    private String sign(String payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(payload.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot sign token", ex);
        }
    }

    private boolean constantTimeEquals(String left, String right) {
        if (left.length() != right.length()) {
            return false;
        }
        int result = 0;
        for (int i = 0; i < left.length(); i++) {
            result |= left.charAt(i) ^ right.charAt(i);
        }
        return result == 0;
    }
}
