package com.ec26b.shoppingagent.auth;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Component;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;

@Component
@ConditionalOnProperty(name = "chat.history-store", havingValue = "postgres")
public class PostgresUserRepository implements UserRepository {

    private final JdbcTemplate jdbc;

    public PostgresUserRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public User save(String username, String passwordHash, String displayName) {
        var keyHolder = new GeneratedKeyHolder();
        jdbc.update(conn -> {
            PreparedStatement ps = conn.prepareStatement(
                    "INSERT INTO users(username, password_hash, display_name, role) VALUES (?, ?, ?, 'USER')",
                    Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, username);
            ps.setString(2, passwordHash);
            ps.setString(3, displayName);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        long id = key != null ? key.longValue() : -1;
        return findById(id).orElseThrow(() -> new IllegalStateException("user not persisted"));
    }

    @Override
    public Optional<User> findByUsername(String username) {
        List<User> result = jdbc.query(
                "SELECT id, username, password_hash, display_name, role, created_at "
                + "FROM users WHERE username = ?",
                (rs, i) -> mapRow(rs),
                username);
        return result.stream().findFirst();
    }

    @Override
    public Optional<User> findById(long id) {
        List<User> result = jdbc.query(
                "SELECT id, username, password_hash, display_name, role, created_at "
                + "FROM users WHERE id = ?",
                (rs, i) -> mapRow(rs),
                id);
        return result.stream().findFirst();
    }

    @Override
    public boolean existsByUsername(String username) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM users WHERE username = ?", Integer.class, username);
        return count != null && count > 0;
    }

    private User mapRow(java.sql.ResultSet rs) throws java.sql.SQLException {
        Timestamp ts = rs.getTimestamp("created_at");
        OffsetDateTime created = ts != null
                ? ts.toInstant().atOffset(ZoneOffset.UTC) : OffsetDateTime.now();
        return new User(
                rs.getLong("id"), rs.getString("username"), rs.getString("password_hash"),
                rs.getString("display_name"), rs.getString("role"), created);
    }
}
