package com.ec26b.shoppingagent.api;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

public final class ApiModels {
    private ApiModels() {
    }

    public record ApiResponse<T>(int code, String message, T data) {
        public static <T> ApiResponse<T> success(T data) {
            return new ApiResponse<>(0, "success", data);
        }

        public static ApiResponse<Void> empty() {
            return new ApiResponse<>(0, "success", null);
        }

        public static ApiResponse<Void> error(int code, String message) {
            return new ApiResponse<>(code, message, null);
        }
    }

    public record PageData<T>(List<T> items, int page, int pageSize, int total) {
    }

    public record Money(String amount, String currency) {
    }

    public record UserDto(long id, String username, String nickname, String avatarUrl, String status) {
    }

    public record RegisterRequest(String username, String password, String nickname) {
    }

    public record LoginRequest(String username, String password) {
    }

    public record RefreshTokenRequest(String refreshToken) {
    }

    public record AuthPayload(String accessToken, String refreshToken, long expiresIn, UserDto user) {
    }

    public record RefreshTokenPayload(String accessToken, String refreshToken, long expiresIn) {
    }

    public record ImageDto(long imageId, String imageUrl, String contentType, long size, OffsetDateTime createdAt) {
    }

    public record CreateRecognitionRequest(long imageId) {
    }

    public record UpdateRecognitionAttributesRequest(
            String category,
            String brand,
            String model,
            Map<String, Object> attributes
    ) {
    }

    public record SuggestionCard(String cardId, String type, String title, Map<String, Object> payload, int priority) {
    }

    public record RecognitionDto(
            long recognitionId,
            long imageId,
            String category,
            String brand,
            String model,
            List<String> keywords,
            Map<String, Object> attributes,
            List<SuggestionCard> suggestionCards,
            double confidence,
            String aiProvider,
            boolean fallbackUsed,
            String explanation,
            List<String> notices,
            String status,
            OffsetDateTime createdAt
    ) {
    }

    public record CreateSearchTaskRequest(
            Long recognitionId,
            String query,
            List<String> platforms,
            String sourceType,
            Map<String, Object> filters,
            String sortBy
    ) {
    }

    public record SearchTaskItemDto(
            long platformProductId,
            long productId,
            String platform,
            String title,
            String imageUrl,
            Money price,
            Money originalPrice,
            String url,
            String shopName,
            List<String> tags,
            int salesVolume,
            double rating,
            boolean isOfficial,
            boolean isSelfOperated,
            double matchScore,
            List<String> matchReasons,
            String sourceType,
            OffsetDateTime updatedAt
    ) {
    }

    public record PlatformStats(String platform, Money lowestPrice, Money averagePrice, int productCount) {
    }

    public record SearchTaskDto(
            long searchTaskId,
            String status,
            String query,
            String sourceType,
            Map<String, Object> filters,
            RecognitionDto recognition,
            List<SearchTaskItemDto> items,
            List<SuggestionCard> suggestionCards,
            List<PlatformStats> platformStats,
            OffsetDateTime createdAt
    ) {
    }

    public record SearchTaskSummaryDto(
            long searchTaskId,
            String query,
            String status,
            String sourceType,
            int resultCount,
            OffsetDateTime createdAt
    ) {
    }

    public record RefineSearchTaskRequest(String text, String sortBy) {
    }

    public record RefineSearchTaskPayload(
            long searchTaskId,
            String text,
            Map<String, Object> filters,
            List<SearchTaskItemDto> items,
            List<SuggestionCard> suggestionCards,
            List<PlatformStats> platformStats,
            String aiProvider,
            boolean fallbackUsed,
            List<String> notices
    ) {
    }

    public record ProductDto(
            long productId,
            String name,
            String category,
            String brand,
            String model,
            Map<String, Object> attributes,
            OffsetDateTime createdAt
    ) {
    }

    public record PlatformProductDto(
            long platformProductId,
            long productId,
            String platform,
            String title,
            String imageUrl,
            Money price,
            Money originalPrice,
            String url,
            String shopName,
            List<String> tags,
            int salesVolume,
            Double rating,
            boolean isOfficial,
            boolean isSelfOperated,
            String sourceType,
            OffsetDateTime updatedAt
    ) {
    }

    public record PricePointDto(OffsetDateTime recordedAt, Money price) {
    }

    public record PriceHistoryDto(
            long platformProductId,
            int days,
            Money currentPrice,
            Money lowestPrice,
            Money highestPrice,
            String trend,
            List<PricePointDto> points
    ) {
    }

    public record ReviewSummaryDto(
            long platformProductId,
            Double rating,
            Integer reviewCount,
            List<String> positiveTags,
            List<String> riskTags,
            double riskScore,
            String summary
    ) {
    }

    public record EcommerceProviderStatus(
            String platform,
            boolean enabled,
            boolean configured,
            List<String> requiredConfig,
            List<String> missingConfig
    ) {
    }

    public record EcommerceStatusPayload(
            boolean enabled,
            boolean hasConfiguredClient,
            List<EcommerceProviderStatus> providers
    ) {
    }

    public record EcommerceProviderDiagnostic(
            String platform,
            boolean configured,
            boolean success,
            String status,
            int itemCount,
            long durationMs,
            List<String> sampleTitles,
            String errorCode,
            String errorMessage,
            List<String> missingConfig
    ) {
    }

    public record EcommerceDiagnosticsPayload(
            String query,
            OffsetDateTime checkedAt,
            List<EcommerceProviderDiagnostic> providers
    ) {
    }

    public record CreateComparisonRequest(long searchTaskId, List<Long> platformProductIds) {
    }

    public record ComparisonDto(
            long comparisonId,
            long searchTaskId,
            Long lowestPlatformProductId,
            Money lowestPrice,
            List<PlatformStats> platformStats,
            List<SearchTaskItemDto> items,
            OffsetDateTime createdAt
    ) {
    }

    public record CreateRecommendationRequest(long searchTaskId, String userQuery, List<Long> candidateIds) {
    }

    public record RecommendationEvidenceDto(String type, Long platformProductId, String content) {
    }

    public record RecommendedPlatformProductDto(
            long platformProductId,
            String platform,
            String title,
            Money price,
            double matchScore
    ) {
    }

    public record RecommendationDto(
            long recommendationId,
            long searchTaskId,
            String suggestion,
            RecommendedPlatformProductDto recommendedPlatformProduct,
            List<String> reasons,
            List<String> risks,
            List<RecommendationEvidenceDto> evidence,
            OffsetDateTime createdAt
    ) {
    }

    public record CreateFavoriteRequest(long platformProductId, String note) {
    }

    public record FavoriteDto(
            long favoriteId,
            long platformProductId,
            String platform,
            String title,
            Money price,
            String note,
            OffsetDateTime createdAt
    ) {
    }

    public record CreatePriceAlertRequest(long platformProductId, Money targetPrice, Boolean enabled) {
    }

    public record UpdatePriceAlertRequest(Money targetPrice, Boolean enabled) {
    }

    public record PriceAlertDto(
            long priceAlertId,
            long platformProductId,
            String title,
            Money currentPrice,
            Money targetPrice,
            boolean enabled,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt
    ) {
    }
}
