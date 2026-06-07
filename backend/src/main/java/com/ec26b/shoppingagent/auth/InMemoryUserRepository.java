package com.ec26b.shoppingagent.auth;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

@Component
@ConditionalOnProperty(name = "chat.history-store", havingValue = "memory", matchIfMissing = true)
public class InMemoryUserRepository implements UserRepository {

    private final ConcurrentHashMap<String, User> byUsername = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<Long, User> byId = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1);

    @Override
    public User save(String username, String passwordHash, String displayName) {
        long id = sequence.getAndIncrement();
        var user = User.newUser(id, username, passwordHash, displayName);
        byUsername.put(username, user);
        byId.put(id, user);
        return user;
    }

    @Override
    public Optional<User> findByUsername(String username) {
        return Optional.ofNullable(byUsername.get(username));
    }

    @Override
    public Optional<User> findById(long id) {
        return Optional.ofNullable(byId.get(id));
    }

    @Override
    public boolean existsByUsername(String username) {
        return byUsername.containsKey(username);
    }
}
