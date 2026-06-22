package com.ec26b.shoppingagent.favorite;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.sql.Timestamp;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;

@Component
@ConditionalOnProperty(name = "app.persistence.store", havingValue = "postgres")
public class PostgresFavoriteRepository implements FavoriteRepository {

    private final JdbcTemplate jdbc;

    public PostgresFavoriteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Favorite add(long userId, FavoritePayload payload) {
        jdbc.update(
                "INSERT INTO favorites(user_id, product_id, title, platform, price, "
                + "shop_name, brand, image_url, product_url) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                + "ON CONFLICT (user_id, product_id) DO UPDATE SET title = EXCLUDED.title, "
                + "platform = EXCLUDED.platform, price = EXCLUDED.price, shop_name = EXCLUDED.shop_name, "
                + "brand = EXCLUDED.brand, image_url = EXCLUDED.image_url, product_url = EXCLUDED.product_url",
                userId, payload.productId(), payload.title(), payload.platform(), payload.price(),
                payload.shopName(), payload.brand(), payload.imageUrl(), payload.productUrl());
        return findByUserAndProduct(userId, payload.productId())
                .orElseThrow(() -> new IllegalStateException("favorite not persisted"));
    }

    @Override
    public List<Favorite> listByUser(long userId) {
        return jdbc.query(
                "SELECT id, user_id, product_id, title, platform, price, shop_name, brand, "
                + "image_url, product_url, created_at FROM favorites "
                + "WHERE user_id = ? ORDER BY created_at DESC",
                (rs, i) -> mapRow(rs), userId);
    }

    @Override
    public Optional<Favorite> findByUserAndProduct(long userId, String productId) {
        List<Favorite> result = jdbc.query(
                "SELECT id, user_id, product_id, title, platform, price, shop_name, brand, "
                + "image_url, product_url, created_at FROM favorites WHERE user_id = ? AND product_id = ?",
                (rs, i) -> mapRow(rs), userId, productId);
        return result.stream().findFirst();
    }

    @Override
    public boolean delete(long userId, String productId) {
        return jdbc.update("DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
                userId, productId) > 0;
    }

    private Favorite mapRow(java.sql.ResultSet rs) throws java.sql.SQLException {
        Timestamp ts = rs.getTimestamp("created_at");
        return new Favorite(rs.getLong("id"), rs.getLong("user_id"),
                rs.getString("product_id"), rs.getString("title"),
                rs.getString("platform"), rs.getDouble("price"),
                rs.getString("shop_name"), rs.getString("brand"),
                rs.getString("image_url"), rs.getString("product_url"),
                ts.toInstant().atOffset(ZoneOffset.UTC));
    }
}
