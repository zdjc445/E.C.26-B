package com.ec26b.shoppingagent.auth;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.Map;
import java.util.Optional;

@Component
public class JwtService {

    private final SecretKey signingKey;
    private final long ttlMinutes;

    public JwtService(@Value("${app.auth.jwt-secret:dev-only-256bit-secret-please-change-me-12345678}") String secret,
                     @Value("${app.auth.jwt-ttl-minutes:1440}") long ttlMinutes) {
        byte[] keyBytes = secret.getBytes(StandardCharsets.UTF_8);
        if (keyBytes.length < 32) {
            byte[] padded = new byte[32];
            System.arraycopy(keyBytes, 0, padded, 0, keyBytes.length);
            keyBytes = padded;
        }
        this.signingKey = Keys.hmacShaKeyFor(keyBytes);
        this.ttlMinutes = ttlMinutes;
    }

    public String issue(User user) {
        Instant now = Instant.now();
        Instant exp = now.plus(ttlMinutes, ChronoUnit.MINUTES);
        return Jwts.builder()
                .subject(String.valueOf(user.id()))
                .claims(Map.of(
                        "username", user.username(),
                        "displayName", user.displayName() == null ? user.username() : user.displayName(),
                        "role", user.role()))
                .issuedAt(Date.from(now))
                .expiration(Date.from(exp))
                .signWith(signingKey)
                .compact();
    }

    public Optional<AuthenticatedUser> parse(String token) {
        if (token == null || token.isBlank()) return Optional.empty();
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(signingKey)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            long userId = Long.parseLong(claims.getSubject());
            String username = claims.get("username", String.class);
            String role = claims.get("role", String.class);
            return Optional.of(new AuthenticatedUser(userId, username, role == null ? "USER" : role));
        } catch (RuntimeException ex) {
            return Optional.empty();
        }
    }

    public long ttlMinutes() {
        return ttlMinutes;
    }

    public record AuthenticatedUser(long userId, String username, String role) {}
}
