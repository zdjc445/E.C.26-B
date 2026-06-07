package com.ec26b.shoppingagent.auth;

import java.time.OffsetDateTime;

public record User(
        Long id,
        String username,
        String passwordHash,
        String displayName,
        String role,
        OffsetDateTime createdAt
) {
    public static User newUser(long id, String username, String passwordHash, String displayName) {
        return new User(id, username, passwordHash, displayName, "USER", OffsetDateTime.now());
    }
}
