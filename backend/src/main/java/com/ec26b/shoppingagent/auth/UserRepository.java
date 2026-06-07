package com.ec26b.shoppingagent.auth;

import java.util.Optional;

public interface UserRepository {

    User save(String username, String passwordHash, String displayName);

    Optional<User> findByUsername(String username);

    Optional<User> findById(long id);

    boolean existsByUsername(String username);
}
