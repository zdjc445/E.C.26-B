package com.ec26b.shoppingagent.persistence;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.MockCatalog;
import com.ec26b.shoppingagent.service.ShoppingService.UserAccount;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;

@Repository
@Profile("postgres")
public class PostgresShoppingStateRepository implements ShoppingStateRepository {
    private static final Logger log = LoggerFactory.getLogger(PostgresShoppingStateRepository.class);

    private final ObjectMapper objectMapper;
    private final MockCatalog catalog;
    private final String url;
    private final String username;
    private final String password;
    private final boolean failFast;

    public PostgresShoppingStateRepository(
            ObjectMapper objectMapper,
            MockCatalog catalog,
            @Value("${spring.datasource.url}") String url,
            @Value("${spring.datasource.username}") String username,
            @Value("${spring.datasource.password}") String password,
            @Value("${app.persistence.fail-fast:true}") boolean failFast
    ) {
        this.objectMapper = objectMapper;
        this.catalog = catalog;
        this.url = url;
        this.username = username;
        this.password = password;
        this.failFast = failFast;
    }

    @PostConstruct
    void seedCatalog() {
        withConnection("seed mock catalog", connection -> {
            for (MockCatalog.ProductData product : catalog.products()) {
                execute(connection, """
                        INSERT INTO products (id, name, category, brand, model, attributes)
                        VALUES (?, ?, ?, ?, ?, ?::jsonb)
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            category = EXCLUDED.category,
                            brand = EXCLUDED.brand,
                            model = EXCLUDED.model,
                            attributes = EXCLUDED.attributes,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        product.productId(), product.name(), product.category(), product.brand(), product.model(), json(product.attributes()));
            }
            for (MockCatalog.PlatformProductData product : catalog.platformProducts()) {
                execute(connection, """
                        INSERT INTO platform_products (
                            id, product_id, platform, title, image_url, price_amount, original_price_amount, currency,
                            url, shop_name, source_type, tags, sales_volume, rating, is_official, is_self_operated
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?, ?, ?, ?)
                        ON CONFLICT (id) DO UPDATE SET
                            product_id = EXCLUDED.product_id,
                            platform = EXCLUDED.platform,
                            title = EXCLUDED.title,
                            image_url = EXCLUDED.image_url,
                            price_amount = EXCLUDED.price_amount,
                            original_price_amount = EXCLUDED.original_price_amount,
                            currency = EXCLUDED.currency,
                            url = EXCLUDED.url,
                            shop_name = EXCLUDED.shop_name,
                            source_type = EXCLUDED.source_type,
                            tags = EXCLUDED.tags,
                            sales_volume = EXCLUDED.sales_volume,
                            rating = EXCLUDED.rating,
                            is_official = EXCLUDED.is_official,
                            is_self_operated = EXCLUDED.is_self_operated,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        product.platformProductId(), product.productId(), product.platform(), product.title(), product.imageUrl(),
                        amount(product.price()), amountOrNull(product.originalPrice()), currency(product.price()), product.url(), product.shopName(),
                        catalog.normalizeSourceType(product.sourceType()), json(product.tags()), product.salesVolume(), product.rating(),
                        product.isOfficial(), product.isSelfOperated());
            }
            for (MockCatalog.PriceHistoryData history : catalog.platformProducts().stream()
                    .map(item -> catalog.priceHistory(item.platformProductId()).orElse(null))
                    .filter(item -> item != null)
                    .toList()) {
                execute(connection, "DELETE FROM price_records WHERE platform_product_id = ?", history.platformProductId());
                for (MockCatalog.PricePointData point : history.points()) {
                    execute(connection, """
                            INSERT INTO price_records (platform_product_id, price_amount, currency, recorded_at)
                            VALUES (?, ?, ?, ?)
                            """, history.platformProductId(), amount(point.price()), currency(point.price()), point.recordedAt());
                }
            }
            for (MockCatalog.PlatformProductData product : catalog.platformProducts()) {
                catalog.reviewSummary(product.platformProductId()).ifPresent(summary ->
                        executeUnchecked(connection, """
                                INSERT INTO review_summaries (platform_product_id, rating, review_count, positive_tags, risk_tags, risk_score, summary)
                                VALUES (?, ?, ?, ?::jsonb, ?::jsonb, ?, ?)
                                ON CONFLICT (platform_product_id) DO UPDATE SET
                                    rating = EXCLUDED.rating,
                                    review_count = EXCLUDED.review_count,
                                    positive_tags = EXCLUDED.positive_tags,
                                    risk_tags = EXCLUDED.risk_tags,
                                    risk_score = EXCLUDED.risk_score,
                                    summary = EXCLUDED.summary,
                                    updated_at = CURRENT_TIMESTAMP
                                """,
                                summary.platformProductId(), summary.rating(), summary.reviewCount(), json(summary.positiveTags()),
                                json(summary.riskTags()), summary.riskScore(), summary.summary()));
            }
        });
    }

    @Override
    public void saveUser(UserAccount user) {
        withConnection("save user", connection -> execute(connection, """
                INSERT INTO users (id, username, password_hash, nickname, avatar_url, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    username = EXCLUDED.username,
                    password_hash = EXCLUDED.password_hash,
                    nickname = EXCLUDED.nickname,
                    avatar_url = EXCLUDED.avatar_url,
                    status = EXCLUDED.status,
                    updated_at = CURRENT_TIMESTAMP
                """, user.id(), user.username(), user.passwordHash(), user.nickname(), user.avatarUrl(), user.status()));
    }

    @Override
    public void saveRefreshSession(String refreshTokenHash, long userId) {
        withConnection("save refresh session", connection -> execute(connection, """
                INSERT INTO user_sessions (user_id, refresh_token_hash, expires_at)
                VALUES (?, ?, ?)
                """, userId, refreshTokenHash, OffsetDateTime.now().plus(30, ChronoUnit.DAYS)));
    }

    @Override
    public void deleteRefreshSession(String refreshTokenHash) {
        withConnection("revoke refresh session", connection -> execute(connection, """
                UPDATE user_sessions SET revoked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE refresh_token_hash = ? AND revoked_at IS NULL
                """, refreshTokenHash));
    }

    @Override
    public void saveImage(long userId, ImageDto image, boolean deleted) {
        withConnection("save image", connection -> execute(connection, """
                INSERT INTO uploaded_images (id, user_id, image_url, content_type, size, deleted_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    image_url = EXCLUDED.image_url,
                    content_type = EXCLUDED.content_type,
                    size = EXCLUDED.size,
                    deleted_at = EXCLUDED.deleted_at
                """, image.imageId(), userId, image.imageUrl(), image.contentType(), image.size(), deleted ? OffsetDateTime.now() : null, image.createdAt()));
    }

    @Override
    public void saveRecognition(long userId, RecognitionDto recognition) {
        withConnection("save recognition", connection -> execute(connection, """
                INSERT INTO recognitions (
                    id, user_id, image_id, category, brand, model, keywords, attributes, suggestion_cards,
                    confidence, ai_provider, fallback_used, explanation, notices, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::jsonb, ?, ?, ?, ?, ?::jsonb, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    category = EXCLUDED.category,
                    brand = EXCLUDED.brand,
                    model = EXCLUDED.model,
                    keywords = EXCLUDED.keywords,
                    attributes = EXCLUDED.attributes,
                    suggestion_cards = EXCLUDED.suggestion_cards,
                    confidence = EXCLUDED.confidence,
                    ai_provider = EXCLUDED.ai_provider,
                    fallback_used = EXCLUDED.fallback_used,
                    explanation = EXCLUDED.explanation,
                    notices = EXCLUDED.notices,
                    status = EXCLUDED.status,
                    updated_at = CURRENT_TIMESTAMP
                """, recognition.recognitionId(), userId, recognition.imageId(), recognition.category(), recognition.brand(), recognition.model(),
                json(recognition.keywords()), json(recognition.attributes()), json(recognition.suggestionCards()), recognition.confidence(),
                recognition.aiProvider(), recognition.fallbackUsed(), recognition.explanation(), json(recognition.notices()),
                recognition.status(), recognition.createdAt()));
    }

    @Override
    public void saveSearchTask(long userId, SearchTaskDto searchTask) {
        withConnection("save search task", connection -> {
            execute(connection, """
                    INSERT INTO search_tasks (
                        id, user_id, recognition_id, query, source_type, filters_snapshot, suggestion_cards, status, result_count, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        query = EXCLUDED.query,
                        source_type = EXCLUDED.source_type,
                        filters_snapshot = EXCLUDED.filters_snapshot,
                        suggestion_cards = EXCLUDED.suggestion_cards,
                        status = EXCLUDED.status,
                        result_count = EXCLUDED.result_count,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    searchTask.searchTaskId(), userId,
                    searchTask.recognition() == null ? null : searchTask.recognition().recognitionId(),
                    searchTask.query(), searchTask.sourceType(), json(searchTask.filters()), json(searchTask.suggestionCards()),
                    searchTask.status(), searchTask.items().size(), searchTask.createdAt());
            execute(connection, "DELETE FROM search_task_items WHERE search_task_id = ?", searchTask.searchTaskId());
            int rank = 1;
            for (SearchTaskItemDto item : searchTask.items()) {
                execute(connection, """
                        INSERT INTO search_task_items (
                            user_id, search_task_id, product_id, platform_product_id, match_score, match_reasons, rank_index, source_type
                        )
                        VALUES (?, ?, ?, ?, ?, ?::jsonb, ?, ?)
                        """, userId, searchTask.searchTaskId(), item.productId(), item.platformProductId(), item.matchScore(), json(item.matchReasons()), rank++, item.sourceType());
            }
        });
    }

    @Override
    public void saveRefinement(long userId, RefineSearchTaskPayload refinement) {
        withConnection("save refinement", connection -> execute(connection, """
                INSERT INTO search_task_refinements (user_id, search_task_id, user_text, parsed_filters, ai_provider, fallback_used, notices, result_count)
                VALUES (?, ?, ?, ?::jsonb, ?, ?, ?::jsonb, ?)
                """, userId, refinement.searchTaskId(), refinement.text(), json(refinement.filters()), refinement.aiProvider(),
                refinement.fallbackUsed(), json(refinement.notices()), refinement.items().size()));
    }

    @Override
    public void saveComparison(long userId, ComparisonDto comparison) {
        withConnection("save comparison", connection -> {
            execute(connection, """
                    INSERT INTO comparisons (id, user_id, search_task_id, lowest_platform_product_id, lowest_price_amount, currency, platform_stats, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?::jsonb, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        lowest_platform_product_id = EXCLUDED.lowest_platform_product_id,
                        lowest_price_amount = EXCLUDED.lowest_price_amount,
                        currency = EXCLUDED.currency,
                        platform_stats = EXCLUDED.platform_stats
                    """, comparison.comparisonId(), userId, comparison.searchTaskId(), comparison.lowestPlatformProductId(),
                    amountOrNull(comparison.lowestPrice()), currency(comparison.lowestPrice()), json(comparison.platformStats()), comparison.createdAt());
            execute(connection, "DELETE FROM comparison_items WHERE comparison_id = ?", comparison.comparisonId());
            for (SearchTaskItemDto item : comparison.items()) {
                execute(connection, """
                        INSERT INTO comparison_items (user_id, comparison_id, platform_product_id, price_amount, currency, match_score, source_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, userId, comparison.comparisonId(), item.platformProductId(), amount(item.price()), currency(item.price()), item.matchScore(), item.sourceType());
            }
        });
    }

    @Override
    public void saveRecommendation(long userId, RecommendationDto recommendation, String userQuery) {
        withConnection("save recommendation", connection -> {
            execute(connection, """
                    INSERT INTO recommendations (
                        id, user_id, search_task_id, user_query, suggestion, recommended_platform_product_id,
                        reasons, risks, output_snapshot, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::jsonb, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        suggestion = EXCLUDED.suggestion,
                        recommended_platform_product_id = EXCLUDED.recommended_platform_product_id,
                        reasons = EXCLUDED.reasons,
                        risks = EXCLUDED.risks,
                        output_snapshot = EXCLUDED.output_snapshot
                    """, recommendation.recommendationId(), userId, recommendation.searchTaskId(), userQuery,
                    recommendation.suggestion(),
                    recommendation.recommendedPlatformProduct() == null ? null : recommendation.recommendedPlatformProduct().platformProductId(),
                    json(recommendation.reasons()), json(recommendation.risks()), json(recommendation), recommendation.createdAt());
            for (RecommendationEvidenceDto evidence : recommendation.evidence()) {
                execute(connection, """
                        INSERT INTO recommendation_evidence (user_id, recommendation_id, evidence_type, platform_product_id, content)
                        VALUES (?, ?, ?, ?, ?)
                        """, userId, recommendation.recommendationId(), evidence.type(), evidence.platformProductId(), evidence.content());
            }
        });
    }

    @Override
    public void saveFavorite(long userId, FavoriteDto favorite) {
        withConnection("save favorite", connection -> execute(connection, """
                INSERT INTO favorites (id, user_id, platform_product_id, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (user_id, platform_product_id) DO UPDATE SET note = EXCLUDED.note
                """, favorite.favoriteId(), userId, favorite.platformProductId(), favorite.note(), favorite.createdAt()));
    }

    @Override
    public void deleteFavorite(long userId, long favoriteId) {
        withConnection("delete favorite", connection -> execute(connection, "DELETE FROM favorites WHERE id = ? AND user_id = ?", favoriteId, userId));
    }

    @Override
    public void savePriceAlert(long userId, PriceAlertDto priceAlert) {
        withConnection("save price alert", connection -> execute(connection, """
                INSERT INTO price_alerts (id, user_id, platform_product_id, target_price_amount, currency, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, platform_product_id) DO UPDATE SET
                    target_price_amount = EXCLUDED.target_price_amount,
                    currency = EXCLUDED.currency,
                    enabled = EXCLUDED.enabled,
                    updated_at = CURRENT_TIMESTAMP
                """, priceAlert.priceAlertId(), userId, priceAlert.platformProductId(), amount(priceAlert.targetPrice()),
                currency(priceAlert.targetPrice()), priceAlert.enabled(), priceAlert.createdAt(), priceAlert.updatedAt()));
    }

    @Override
    public void deletePriceAlert(long userId, long priceAlertId) {
        withConnection("delete price alert", connection -> execute(connection, "DELETE FROM price_alerts WHERE id = ? AND user_id = ?", priceAlertId, userId));
    }

    private void withConnection(String action, SqlWork work) {
        try (Connection connection = DriverManager.getConnection(url, username, password)) {
            work.run(connection);
        } catch (Exception ex) {
            if (failFast) {
                throw new IllegalStateException("PostgreSQL persistence failed during " + action, ex);
            }
            log.warn("PostgreSQL persistence skipped during {}: {}", action, ex.getMessage());
        }
    }

    private void executeUnchecked(Connection connection, String sql, Object... params) {
        try {
            execute(connection, sql, params);
        } catch (SQLException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private void execute(Connection connection, String sql, Object... params) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            for (int i = 0; i < params.length; i++) {
                statement.setObject(i + 1, params[i]);
            }
            statement.executeUpdate();
        }
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("failed to serialize JSON snapshot", ex);
        }
    }

    private BigDecimal amount(Money money) {
        return new BigDecimal(money.amount());
    }

    private BigDecimal amountOrNull(Money money) {
        return money == null ? null : amount(money);
    }

    private String currency(Money money) {
        return money == null ? "CNY" : money.currency();
    }

    @FunctionalInterface
    private interface SqlWork {
        void run(Connection connection) throws Exception;
    }
}
