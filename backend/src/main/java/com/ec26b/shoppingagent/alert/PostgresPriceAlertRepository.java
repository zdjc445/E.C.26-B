package com.ec26b.shoppingagent.alert;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Component;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;

@Component
@ConditionalOnProperty(name = "app.persistence.store", havingValue = "postgres")
public class PostgresPriceAlertRepository implements PriceAlertRepository {

    private final JdbcTemplate jdbc;

    public PostgresPriceAlertRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public PriceAlert create(long userId, PriceAlertPayload payload) {
        var keyHolder = new GeneratedKeyHolder();
        jdbc.update(conn -> {
            PreparedStatement ps = conn.prepareStatement(
                    "INSERT INTO price_alerts(user_id, product_id, title, platform, target_price, note) "
                    + "VALUES (?, ?, ?, ?, ?, ?)",
                    Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, userId);
            ps.setString(2, payload.productId());
            ps.setString(3, payload.title());
            ps.setString(4, payload.platform());
            ps.setDouble(5, payload.targetPrice());
            ps.setString(6, payload.note());
            return ps;
        }, keyHolder);
        long id = keyHolder.getKey() != null ? keyHolder.getKey().longValue() : -1;
        return findById(userId, id).orElseThrow(() -> new IllegalStateException("alert not persisted"));
    }

    @Override
    public List<PriceAlert> listByUser(long userId) {
        return jdbc.query(
                "SELECT id, user_id, product_id, title, platform, target_price, triggered, "
                + "last_observed_price, note, created_at FROM price_alerts "
                + "WHERE user_id = ? ORDER BY created_at DESC",
                (rs, i) -> mapRow(rs), userId);
    }

    @Override
    public Optional<PriceAlert> findById(long userId, long alertId) {
        List<PriceAlert> result = jdbc.query(
                "SELECT id, user_id, product_id, title, platform, target_price, triggered, "
                + "last_observed_price, note, created_at FROM price_alerts WHERE user_id = ? AND id = ?",
                (rs, i) -> mapRow(rs), userId, alertId);
        return result.stream().findFirst();
    }

    @Override
    public Optional<PriceAlert> markObserved(long userId, long alertId, double observedPrice, boolean triggered) {
        int rows = jdbc.update(
                "UPDATE price_alerts SET last_observed_price = ?, triggered = ? "
                + "WHERE user_id = ? AND id = ?",
                observedPrice, triggered, userId, alertId);
        if (rows == 0) return Optional.empty();
        return findById(userId, alertId);
    }

    @Override
    public boolean delete(long userId, long alertId) {
        return jdbc.update("DELETE FROM price_alerts WHERE user_id = ? AND id = ?",
                userId, alertId) > 0;
    }

    private PriceAlert mapRow(ResultSet rs) throws SQLException {
        Timestamp ts = rs.getTimestamp("created_at");
        double observed = rs.getDouble("last_observed_price");
        boolean hasObserved = !rs.wasNull();
        return new PriceAlert(rs.getLong("id"), rs.getLong("user_id"),
                rs.getString("product_id"), rs.getString("title"),
                rs.getString("platform"), rs.getDouble("target_price"),
                rs.getBoolean("triggered"),
                hasObserved ? observed : null,
                rs.getString("note"),
                ts.toInstant().atOffset(ZoneOffset.UTC));
    }
}
