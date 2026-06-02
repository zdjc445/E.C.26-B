package com.ec26b.shoppingagent.service;

import com.ec26b.shoppingagent.api.ApiException;
import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.ai.AiRecognitionProvider;
import com.ec26b.shoppingagent.ai.AiRefineProvider;
import com.ec26b.shoppingagent.ai.ImagePayload;
import com.ec26b.shoppingagent.ai.RecognitionResult;
import com.ec26b.shoppingagent.ai.RefineParseResult;
import com.ec26b.shoppingagent.ecommerce.OfficialProductSourceProvider;
import com.ec26b.shoppingagent.ecommerce.ProductSourceQuery;
import com.ec26b.shoppingagent.persistence.ShoppingStateRepository;
import com.ec26b.shoppingagent.security.JwtService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

@Service
public class ShoppingService {
    private static final Set<String> SOURCE_TYPES = Set.of("mock", "official_api", "sample_dataset");
    private static final Set<String> SORT_MODES = Set.of("comprehensive", "price_asc", "sales_desc", "rating_desc");

    private final MockCatalog catalog;
    private final OfficialProductSourceProvider officialProductSource;
    private final AiRecognitionProvider recognitionProvider;
    private final AiRefineProvider refineProvider;
    private final ShoppingStateRepository stateRepository;
    private final JwtService jwtService;
    private final PasswordEncoder passwordEncoder;
    private final String uploadDir;
    private final SecureRandom secureRandom = new SecureRandom();

    private final AtomicLong userIds = new AtomicLong(1);
    private final AtomicLong imageIds = new AtomicLong(1001);
    private final AtomicLong recognitionIds = new AtomicLong(2001);
    private final AtomicLong searchTaskIds = new AtomicLong(3001);
    private final AtomicLong comparisonIds = new AtomicLong(6001);
    private final AtomicLong recommendationIds = new AtomicLong(7001);
    private final AtomicLong favoriteIds = new AtomicLong(8001);
    private final AtomicLong priceAlertIds = new AtomicLong(9001);

    private final Map<Long, UserAccount> users = new ConcurrentHashMap<>();
    private final Map<String, Long> usernameIndex = new ConcurrentHashMap<>();
    private final Map<String, Long> refreshSessions = new ConcurrentHashMap<>();
    private final Map<Long, ImageRecord> images = new ConcurrentHashMap<>();
    private final Map<Long, RecognitionRecord> recognitions = new ConcurrentHashMap<>();
    private final Map<Long, SearchTaskRecord> searchTasks = new ConcurrentHashMap<>();
    private final Map<Long, ComparisonRecord> comparisons = new ConcurrentHashMap<>();
    private final Map<Long, RecommendationDto> recommendations = new ConcurrentHashMap<>();
    private final Map<Long, FavoriteRecord> favorites = new ConcurrentHashMap<>();
    private final Map<Long, PriceAlertRecord> priceAlerts = new ConcurrentHashMap<>();

    public ShoppingService(
            MockCatalog catalog,
            OfficialProductSourceProvider officialProductSource,
            AiRecognitionProvider recognitionProvider,
            AiRefineProvider refineProvider,
            ShoppingStateRepository stateRepository,
            JwtService jwtService,
            PasswordEncoder passwordEncoder,
            @Value("${app.upload-dir}") String uploadDir
    ) {
        this.catalog = catalog;
        this.officialProductSource = officialProductSource;
        this.recognitionProvider = recognitionProvider;
        this.refineProvider = refineProvider;
        this.stateRepository = stateRepository;
        this.jwtService = jwtService;
        this.passwordEncoder = passwordEncoder;
        this.uploadDir = uploadDir;
    }

    public UserAccount requireUser(long userId) {
        UserAccount user = users.get(userId);
        if (user == null || !"active".equals(user.status())) {
            throw ApiException.unauthorized("user not found");
        }
        return user;
    }

    public AuthPayload register(RegisterRequest request) {
        String username = requireText(request.username(), "username");
        String password = requireText(request.password(), "password");
        if (username.length() < 3 || username.length() > 32 || password.length() < 8) {
            throw new ApiException(42201, "username or password format invalid", org.springframework.http.HttpStatus.UNPROCESSABLE_ENTITY);
        }
        if (usernameIndex.containsKey(username)) {
            throw ApiException.conflict(40901, "username already exists");
        }
        long id = userIds.getAndIncrement();
        UserAccount user = new UserAccount(id, username, passwordEncoder.encode(password), request.nickname(), null, "active");
        users.put(id, user);
        usernameIndex.put(username, id);
        stateRepository.saveUser(user);
        return issueAuth(user);
    }

    public AuthPayload login(LoginRequest request) {
        Long userId = usernameIndex.get(requireText(request.username(), "username"));
        if (userId == null) {
            throw ApiException.unauthorized("invalid username or password");
        }
        UserAccount user = users.get(userId);
        if (!passwordEncoder.matches(requireText(request.password(), "password"), user.passwordHash())) {
            throw ApiException.unauthorized("invalid username or password");
        }
        return issueAuth(user);
    }

    public RefreshTokenPayload refresh(RefreshTokenRequest request) {
        String hash = hashToken(requireText(request.refreshToken(), "refreshToken"));
        Long userId = refreshSessions.remove(hash);
        stateRepository.deleteRefreshSession(hash);
        if (userId == null) {
            throw new ApiException(40103, "refresh token invalid or expired", org.springframework.http.HttpStatus.UNAUTHORIZED);
        }
        UserAccount user = requireUser(userId);
        AuthPayload payload = issueAuth(user);
        return new RefreshTokenPayload(payload.accessToken(), payload.refreshToken(), payload.expiresIn());
    }

    public void logout(RefreshTokenRequest request) {
        if (request != null && request.refreshToken() != null) {
            String hash = hashToken(request.refreshToken());
            refreshSessions.remove(hash);
            stateRepository.deleteRefreshSession(hash);
        }
    }

    public UserDto currentUser(long userId) {
        return toUserDto(requireUser(userId));
    }

    public ImageDto uploadImage(long userId, MultipartFile file, String scene) {
        requireUser(userId);
        if (file == null || file.isEmpty()) {
            throw new ApiException(42202, "image file required", org.springframework.http.HttpStatus.UNPROCESSABLE_ENTITY);
        }
        String contentType = file.getContentType() == null ? "application/octet-stream" : file.getContentType();
        String originalName = file.getOriginalFilename();
        if (!contentType.startsWith("image/") && looksLikeImage(originalName)) {
            contentType = originalName.toLowerCase(Locale.ROOT).endsWith(".png") ? "image/png" : "image/jpeg";
        }
        if (!contentType.startsWith("image/")) {
            throw new ApiException(42202, "only image upload is allowed", org.springframework.http.HttpStatus.UNPROCESSABLE_ENTITY);
        }
        long id = imageIds.getAndIncrement();
        String extension = extension(originalName, contentType);
        String filename = id + "-" + basename(originalName) + "-" + UUID.randomUUID() + extension;
        Path root = resolveUploadsPath();
        try {
            Files.createDirectories(root);
            Files.copy(file.getInputStream(), root.resolve(filename));
        } catch (IOException ex) {
            throw new ApiException(50001, "image upload failed", org.springframework.http.HttpStatus.INTERNAL_SERVER_ERROR);
        }
        ImageRecord record = new ImageRecord(id, userId, "/uploads/" + filename, contentType, file.getSize(), OffsetDateTime.now(), false);
        images.put(id, record);
        ImageDto dto = toImageDto(record);
        stateRepository.saveImage(userId, dto, false);
        return dto;
    }

    public PageData<ImageDto> imagePage(long userId, int page, int pageSize) {
        requireUser(userId);
        List<ImageDto> items = images.values().stream()
                .filter(item -> item.userId() == userId && !item.deleted())
                .sorted(Comparator.comparing(ImageRecord::createdAt).reversed())
                .map(this::toImageDto)
                .toList();
        return page(items, page, pageSize);
    }

    public void deleteImage(long userId, long imageId) {
        ImageRecord record = imageForUser(userId, imageId);
        ImageRecord deleted = new ImageRecord(record.imageId(), record.userId(), record.imageUrl(), record.contentType(), record.size(), record.createdAt(), true);
        images.put(imageId, deleted);
        stateRepository.saveImage(userId, toImageDto(deleted), true);
    }

    public RecognitionDto createRecognition(long userId, CreateRecognitionRequest request) {
        ImageRecord image = imageForUser(userId, request.imageId());
        RecognitionResult result = recognitionProvider.recognize(imagePayload(image));
        long id = recognitionIds.getAndIncrement();
        RecognitionRecord record = new RecognitionRecord(
                id,
                userId,
                image.imageId(),
                result.category(),
                result.brand(),
                result.model(),
                safeList(result.keywords()),
                safeMap(result.attributes()),
                result.confidence(),
                result.provider(),
                result.fallbackUsed(),
                result.explanation(),
                safeList(result.notices()),
                "succeeded",
                OffsetDateTime.now()
        );
        record.suggestionCards = suggestionCards(record.category, record.attributes, Map.of());
        recognitions.put(id, record);
        RecognitionDto dto = toRecognitionDto(record);
        stateRepository.saveRecognition(userId, dto);
        return dto;
    }

    public RecognitionDto recognition(long userId, long recognitionId) {
        return toRecognitionDto(recognitionForUser(userId, recognitionId));
    }

    public RecognitionDto updateRecognition(long userId, long recognitionId, UpdateRecognitionAttributesRequest request) {
        RecognitionRecord record = recognitionForUser(userId, recognitionId);
        if (request.category() != null && !request.category().isBlank()) {
            record.category = request.category();
        }
        if (request.brand() != null) {
            record.brand = request.brand();
        }
        if (request.model() != null) {
            record.model = request.model();
        }
        if (request.attributes() != null) {
            record.attributes = new LinkedHashMap<>(request.attributes());
        }
        record.suggestionCards = suggestionCards(record.category, record.attributes, Map.of());
        RecognitionDto dto = toRecognitionDto(record);
        stateRepository.saveRecognition(userId, dto);
        return dto;
    }

    public SearchTaskDto createSearchTask(long userId, CreateSearchTaskRequest request) {
        requireUser(userId);
        RecognitionRecord recognition = null;
        if (request.recognitionId() != null) {
            recognition = recognitionForUser(userId, request.recognitionId());
        }
        if (recognition == null && isBlank(request.query())) {
            throw ApiException.badRequest("recognitionId or query is required");
        }
        Map<String, Object> filters = new LinkedHashMap<>();
        if (request.filters() != null) {
            filters.putAll(request.filters());
        }
        RefineParseResult parsedQuery = parseFilters(request.query(), filters);
        filters.putAll(parsedQuery.filters());
        if (request.platforms() != null && !request.platforms().isEmpty()) {
            filters.put("platforms", request.platforms());
        }
        if (!isBlank(request.sortBy())) {
            filters.put("sortBy", normalizeSort(request.sortBy()));
        }
        filters.putIfAbsent("sortBy", "comprehensive");
        String sourceType = normalizeSourceType(request.sourceType());
        List<SearchTaskItemDto> items = buildItems(request.query(), recognition, filters, sourceType);
        List<SuggestionCard> cards = suggestionCards(recognition == null ? null : recognition.category, recognition == null ? Map.of() : recognition.attributes, filters);
        long id = searchTaskIds.getAndIncrement();
        SearchTaskRecord task = new SearchTaskRecord(
                id,
                userId,
                recognition == null ? null : recognition.id,
                request.query(),
                sourceType,
                filters,
                "succeeded",
                items,
                cards,
                platformStats(items),
                OffsetDateTime.now()
        );
        searchTasks.put(id, task);
        SearchTaskDto dto = toSearchTaskDto(task);
        stateRepository.saveSearchTask(userId, dto);
        return dto;
    }

    public SearchTaskDto searchTask(long userId, long searchTaskId) {
        return toSearchTaskDto(searchTaskForUser(userId, searchTaskId));
    }

    public PageData<SearchTaskSummaryDto> searchHistory(long userId, int page, int pageSize) {
        requireUser(userId);
        List<SearchTaskSummaryDto> items = searchTasks.values().stream()
                .filter(item -> item.userId == userId)
                .sorted(Comparator.comparing((SearchTaskRecord item) -> item.createdAt).reversed())
                .map(item -> new SearchTaskSummaryDto(item.id, item.query, item.status, item.sourceType, item.items.size(), item.createdAt))
                .toList();
        return page(items, page, pageSize);
    }

    public RefineSearchTaskPayload refineSearchTask(long userId, long searchTaskId, RefineSearchTaskRequest request) {
        SearchTaskRecord task = searchTaskForUser(userId, searchTaskId);
        String text = requireText(request.text(), "text");
        RefineParseResult parsedResult = parseFilters(text, task.filters);
        Map<String, Object> parsed = new LinkedHashMap<>(parsedResult.filters());
        if (!isBlank(request.sortBy())) {
            parsed.put("sortBy", normalizeSort(request.sortBy()));
        }
        Map<String, Object> filters = new LinkedHashMap<>(task.filters);
        filters.putAll(parsed);
        filters.putIfAbsent("sortBy", "comprehensive");
        RecognitionRecord recognition = task.recognitionId == null ? null : recognitions.get(task.recognitionId);
        List<SearchTaskItemDto> items = buildItems(task.query + " " + text, recognition, filters, task.sourceType);
        task.filters = filters;
        task.items = items;
        task.suggestionCards = suggestionCards(recognition == null ? null : recognition.category, recognition == null ? Map.of() : recognition.attributes, filters);
        task.platformStats = platformStats(items);
        RefineSearchTaskPayload payload = new RefineSearchTaskPayload(task.id, text, filters, task.items, task.suggestionCards, task.platformStats, parsedResult.provider(), parsedResult.fallbackUsed(), parsedResult.notices());
        stateRepository.saveSearchTask(userId, toSearchTaskDto(task));
        stateRepository.saveRefinement(userId, payload);
        return payload;
    }

    public ProductDto product(long productId) {
        return toProductDto(productData(productId));
    }

    public PlatformProductDto platformProduct(long platformProductId) {
        return toPlatformProductDto(platformProductData(platformProductId));
    }

    public ReviewSummaryDto reviewSummary(long platformProductId) {
        platformProductData(platformProductId);
        return reviewSummaryData(platformProductId)
                .map(this::toReviewSummaryDto)
                .orElseGet(() -> new ReviewSummaryDto(platformProductId, null, 0, List.of(), List.of(), 0.5, "暂无评价摘要，已使用中性风险兜底。"));
    }

    public PriceHistoryDto priceHistory(long platformProductId, int days) {
        MockCatalog.PlatformProductData product = platformProductData(platformProductId);
        List<MockCatalog.PricePointData> points = priceHistoryData(platformProductId)
                .map(MockCatalog.PriceHistoryData::points)
                .orElse(List.of()).stream()
                .sorted(Comparator.comparing(MockCatalog.PricePointData::recordedAt))
                .toList();
        if (points.isEmpty()) {
            return new PriceHistoryDto(platformProductId, days, product.price(), product.price(), product.price(), "unknown", List.of());
        }
        List<PricePointDto> pointDtos = points.stream()
                .map(point -> new PricePointDto(point.recordedAt(), point.price()))
                .toList();
        Money current = points.get(points.size() - 1).price();
        Money lowest = points.stream().min(Comparator.comparing(point -> amount(point.price()))).orElseThrow().price();
        Money highest = points.stream().max(Comparator.comparing(point -> amount(point.price()))).orElseThrow().price();
        BigDecimal currentAmount = amount(current);
        String trend = "normal";
        if (currentAmount.compareTo(amount(lowest).multiply(new BigDecimal("1.05"))) <= 0) {
            trend = "low";
        } else if (currentAmount.compareTo(amount(highest).multiply(new BigDecimal("0.95"))) >= 0) {
            trend = "high";
        }
        return new PriceHistoryDto(platformProductId, days, current, lowest, highest, trend, pointDtos);
    }

    public ComparisonDto createComparison(long userId, CreateComparisonRequest request) {
        SearchTaskRecord task = searchTaskForUser(userId, request.searchTaskId());
        Set<Long> allowed = task.items.stream().map(SearchTaskItemDto::platformProductId).collect(Collectors.toSet());
        List<Long> ids = request.platformProductIds() == null || request.platformProductIds().isEmpty()
                ? new ArrayList<>(allowed)
                : request.platformProductIds();
        if (ids.isEmpty()) {
            throw ApiException.badRequest("platformProductIds is empty");
        }
        List<SearchTaskItemDto> items = task.items.stream()
                .filter(item -> ids.contains(item.platformProductId()))
                .toList();
        if (items.size() != ids.size() || !allowed.containsAll(ids)) {
            throw ApiException.notFound(40405, "platform product not found in search task");
        }
        SearchTaskItemDto lowest = items.stream()
                .min(Comparator.comparing(item -> amount(item.price())))
                .orElseThrow();
        long id = comparisonIds.getAndIncrement();
        ComparisonDto dto = new ComparisonDto(id, task.id, lowest.platformProductId(), lowest.price(), platformStats(items), items, OffsetDateTime.now());
        comparisons.put(id, new ComparisonRecord(id, userId, dto));
        stateRepository.saveComparison(userId, dto);
        return dto;
    }

    public RecommendationDto createRecommendation(long userId, CreateRecommendationRequest request) {
        SearchTaskRecord task = searchTaskForUser(userId, request.searchTaskId());
        List<SearchTaskItemDto> candidates = task.items.stream()
                .filter(item -> request.candidateIds() == null || request.candidateIds().isEmpty() || request.candidateIds().contains(item.platformProductId()))
                .toList();
        if (candidates.isEmpty()) {
            throw ApiException.badRequest("candidateIds is empty or not in search task");
        }
        List<CandidateDecision> rankedCandidates = candidates.stream()
                .map(this::candidateDecision)
                .sorted((left, right) -> {
                    int score = Integer.compare(right.decisionScore(), left.decisionScore());
                    if (score != 0) {
                        return score;
                    }
                    return Double.compare(recommendationScore(right.item()), recommendationScore(left.item()));
                })
                .toList();
        CandidateDecision bestDecision = rankedCandidates.get(0);
        SearchTaskItemDto best = bestDecision.item();
        ReviewSummaryDto review = bestDecision.review();
        PriceHistoryDto history = bestDecision.history();
        List<RecommendationSignalDto> decisionSignals = bestDecision.signals();
        int decisionScore = bestDecision.decisionScore();
        BigDecimal current = amount(best.price());
        BigDecimal historicalLow = amount(history.lowestPrice());
        String suggestion = signalScore(decisionSignals, "risk") < 65
                ? "avoid"
                : current.compareTo(historicalLow.multiply(new BigDecimal("1.12"))) > 0 || signalScore(decisionSignals, "price") < 70
                ? "wait"
                : "buy";
        List<String> reasons = new ArrayList<>();
        reasons.add("匹配分 " + formatDouble(best.matchScore()) + "，与当前识别或搜索意图接近。");
        reasons.add("当前价格 " + best.price().amount() + " CNY，处于候选商品中靠前位置。");
        reasons.add("综合决策分 " + decisionScore + "，由匹配、价格、口碑、渠道和风险五类信号加权得到。");
        reasons.add("已对 " + rankedCandidates.size() + " 个候选商品生成胜因/败因矩阵，推荐结果来自同一套评分规则。");
        if (best.isOfficial() || best.isSelfOperated()) {
            reasons.add("官方或自营渠道确定性更高，适合比赛演示中的可信推荐。");
        }
        List<String> risks = new ArrayList<>();
        if (review.riskTags() != null && !review.riskTags().isEmpty()) {
            risks.add("评价风险：" + String.join("、", review.riskTags()));
        }
        if (!"low".equals(history.trend())) {
            risks.add("历史价格趋势为 " + history.trend() + "，可继续观察降价。");
        }
        List<RecommendationEvidenceDto> evidence = List.of(
                new RecommendationEvidenceDto("price", best.platformProductId(), "当前价 " + best.price().amount() + " CNY。"),
                new RecommendationEvidenceDto("match", best.platformProductId(), "匹配分 " + formatDouble(best.matchScore()) + "。"),
                new RecommendationEvidenceDto("review", best.platformProductId(), "评价风险分 " + formatDouble(review.riskScore()) + "，评分 " + best.rating() + "。"),
                new RecommendationEvidenceDto("history", best.platformProductId(), "90 天历史低价 " + history.lowestPrice().amount() + " CNY。")
        );
        List<RecommendationTraceStepDto> decisionTrace = decisionTrace(task, candidates, best, review, history, decisionSignals, suggestion, decisionScore);
        List<RecommendationCandidateDto> candidateAnalyses = candidateAnalyses(rankedCandidates);
        long id = recommendationIds.getAndIncrement();
        RecommendationDto dto = new RecommendationDto(
                id,
                task.id,
                suggestion,
                new RecommendedPlatformProductDto(best.platformProductId(), best.platform(), best.title(), best.price(), best.matchScore()),
                decisionScore,
                decisionSignals,
                decisionTrace,
                candidateAnalyses,
                reasons,
                risks,
                evidence,
                OffsetDateTime.now()
        );
        recommendations.put(id, dto);
        stateRepository.saveRecommendation(userId, dto, request.userQuery());
        return dto;
    }

    public RecommendationDto recommendation(long userId, long recommendationId) {
        RecommendationDto dto = recommendations.get(recommendationId);
        if (dto == null || searchTaskForUser(userId, dto.searchTaskId()) == null) {
            throw ApiException.notFound(40408, "recommendation not found");
        }
        return dto;
    }

    public RecommendationReportDto recommendationReport(long userId, long recommendationId) {
        RecommendationDto dto = recommendation(userId, recommendationId);
        SearchTaskRecord task = searchTaskForUser(userId, dto.searchTaskId());
        String title = "购物决策证据报告 #" + dto.recommendationId();
        String summary = recommendationSummary(dto, task);
        return new RecommendationReportDto(
                dto.recommendationId(),
                dto.searchTaskId(),
                title,
                summary,
                recommendationMarkdown(dto, task, summary),
                OffsetDateTime.now()
        );
    }

    public FavoriteDto createFavorite(long userId, CreateFavoriteRequest request) {
        requireUser(userId);
        MockCatalog.PlatformProductData product = platformProductData(request.platformProductId());
        boolean exists = favorites.values().stream()
                .anyMatch(item -> item.userId == userId && item.platformProductId == product.platformProductId());
        if (exists) {
            throw ApiException.conflict(40902, "product already favorited");
        }
        FavoriteRecord record = new FavoriteRecord(favoriteIds.getAndIncrement(), userId, product.platformProductId(), request.note(), OffsetDateTime.now());
        favorites.put(record.id, record);
        FavoriteDto dto = toFavoriteDto(record);
        stateRepository.saveFavorite(userId, dto);
        return dto;
    }

    public PageData<FavoriteDto> favorites(long userId, int page, int pageSize) {
        requireUser(userId);
        List<FavoriteDto> items = favorites.values().stream()
                .filter(item -> item.userId == userId)
                .sorted(Comparator.comparing((FavoriteRecord item) -> item.createdAt).reversed())
                .map(this::toFavoriteDto)
                .toList();
        return page(items, page, pageSize);
    }

    public void deleteFavorite(long userId, long favoriteId) {
        FavoriteRecord record = favorites.get(favoriteId);
        if (record == null || record.userId != userId) {
            throw ApiException.notFound(40406, "favorite not found");
        }
        favorites.remove(favoriteId);
        stateRepository.deleteFavorite(userId, favoriteId);
    }

    public PriceAlertDto createPriceAlert(long userId, CreatePriceAlertRequest request) {
        requireUser(userId);
        MockCatalog.PlatformProductData product = platformProductData(request.platformProductId());
        boolean exists = priceAlerts.values().stream()
                .anyMatch(item -> item.userId == userId && item.platformProductId == product.platformProductId());
        if (exists) {
            throw ApiException.conflict(40903, "price alert already exists");
        }
        PriceAlertRecord record = new PriceAlertRecord(
                priceAlertIds.getAndIncrement(),
                userId,
                product.platformProductId(),
                request.targetPrice(),
                request.enabled() == null || request.enabled(),
                OffsetDateTime.now(),
                null
        );
        priceAlerts.put(record.id, record);
        PriceAlertDto dto = toPriceAlertDto(record);
        stateRepository.savePriceAlert(userId, dto);
        return dto;
    }

    public PageData<PriceAlertDto> priceAlerts(long userId, int page, int pageSize) {
        requireUser(userId);
        List<PriceAlertDto> items = priceAlerts.values().stream()
                .filter(item -> item.userId == userId)
                .sorted(Comparator.comparing((PriceAlertRecord item) -> item.createdAt).reversed())
                .map(this::toPriceAlertDto)
                .toList();
        return page(items, page, pageSize);
    }

    public PriceAlertDto updatePriceAlert(long userId, long priceAlertId, UpdatePriceAlertRequest request) {
        PriceAlertRecord record = priceAlertForUser(userId, priceAlertId);
        PriceAlertRecord updated = new PriceAlertRecord(
                record.id,
                record.userId,
                record.platformProductId,
                request.targetPrice() == null ? record.targetPrice : request.targetPrice(),
                request.enabled() == null ? record.enabled : request.enabled(),
                record.createdAt,
                OffsetDateTime.now()
        );
        priceAlerts.put(record.id, updated);
        PriceAlertDto dto = toPriceAlertDto(updated);
        stateRepository.savePriceAlert(userId, dto);
        return dto;
    }

    public void deletePriceAlert(long userId, long priceAlertId) {
        priceAlertForUser(userId, priceAlertId);
        priceAlerts.remove(priceAlertId);
        stateRepository.deletePriceAlert(userId, priceAlertId);
    }

    private List<MockCatalog.PlatformProductData> sourceCandidates(String query, RecognitionRecord recognition, Map<String, Object> filters, String sourceType) {
        if ("official_api".equals(sourceType)) {
            if (!officialProductSource.hasConfiguredClient()) {
                throw ApiException.badRequest("official_api not configured; enable PDD_API_ENABLED or JD_API_ENABLED and provide platform credentials");
            }
            ProductSourceQuery sourceQuery = new ProductSourceQuery(
                    productSearchKeyword(query, recognition),
                    recognition == null ? stringFilter(filters, "category") : firstNonBlank(recognition.category, stringFilter(filters, "category")),
                    recognition == null ? stringFilter(filters, "brand") : firstNonBlank(recognition.brand, stringFilter(filters, "brand")),
                    recognition == null ? null : recognition.model,
                    filters == null ? Map.of() : filters,
                    platformFilters(filters),
                    filters == null ? "comprehensive" : String.valueOf(filters.getOrDefault("sortBy", "comprehensive")),
                    30
            );
            return officialProductSource.search(sourceQuery);
        }
        return catalog.platformProducts();
    }

    private List<SearchTaskItemDto> buildItems(String query, RecognitionRecord recognition, Map<String, Object> filters, String sourceType) {
        List<ScoredProduct> scored = sourceCandidates(query, recognition, filters, sourceType).stream()
                .filter(item -> sourceType.equals(normalizeSourceType(item.sourceType())))
                .filter(item -> matchesFilters(item, filters))
                .map(item -> new ScoredProduct(item, matchScore(item, query, recognition)))
                .filter(item -> recognition == null || item.score >= 0.55 || contains(item.product().title(), recognition.category))
                .sorted(comparatorFor(String.valueOf(filters.getOrDefault("sortBy", "comprehensive"))))
                .toList();
        return scored.stream()
                .map(item -> toSearchTaskItem(item.product(), item.score(), recognition, filters))
                .toList();
    }

    private String productSearchKeyword(String query, RecognitionRecord recognition) {
        List<String> parts = new ArrayList<>();
        if (recognition != null) {
            parts.add(recognition.category);
            parts.add(recognition.brand);
            parts.add(recognition.model);
            parts.addAll(recognition.keywords.stream().limit(3).toList());
        }
        parts.add(query);
        String keyword = parts.stream()
                .filter(value -> value != null && !value.isBlank())
                .distinct()
                .collect(Collectors.joining(" "))
                .trim();
        return keyword.isBlank() ? "商品" : keyword;
    }

    private String stringFilter(Map<String, Object> filters, String key) {
        if (filters == null || !filters.containsKey(key) || filters.get(key) == null) {
            return null;
        }
        String value = String.valueOf(filters.get(key)).trim();
        return value.isBlank() ? null : value;
    }

    private List<String> platformFilters(Map<String, Object> filters) {
        if (filters == null || !filters.containsKey("platforms") || filters.get("platforms") == null) {
            return List.of();
        }
        Object value = filters.get("platforms");
        if (value instanceof List<?> list) {
            return list.stream()
                    .flatMap(item -> java.util.Arrays.stream(String.valueOf(item).split(",")))
                    .map(String::trim)
                    .filter(item -> !item.isBlank())
                    .toList();
        }
        return java.util.Arrays.stream(String.valueOf(value).split(","))
                .map(String::trim)
                .filter(item -> !item.isBlank())
                .toList();
    }

    private double matchScore(MockCatalog.PlatformProductData item, String query, RecognitionRecord recognition) {
        MockCatalog.ProductData product = productData(item.productId());
        String text = normalize((query == null ? "" : query) + " " + item.title() + " " + product.name() + " " + item.tags());
        double score = 0.35;
        if (recognition != null) {
            if (contains(product.category(), recognition.category) || contains(item.title(), recognition.category)) {
                score += 0.20;
            }
            for (String keyword : recognition.keywords) {
                if (contains(text, keyword)) {
                    score += 0.035;
                }
            }
            Object color = recognition.attributes.get("color");
            if (color != null && contains(text, String.valueOf(color))) {
                score += 0.03;
            }
        }
        if (!isBlank(query)) {
            for (String keyword : List.of("低噪", "宿舍", "黑色", "官方", "自营", "降噪", "保湿", "缓震", "茶轴", "5G")) {
                if (contains(query, keyword) && contains(text, keyword)) {
                    score += 0.03;
                }
            }
        }
        if (item.isOfficial()) {
            score += 0.02;
        }
        if (item.isSelfOperated()) {
            score += 0.02;
        }
        score += Math.min(0.06, Math.max(0, item.rating() - 4.4) * 0.05);
        return Math.min(0.99, score);
    }

    private boolean matchesFilters(MockCatalog.PlatformProductData item, Map<String, Object> filters) {
        if (filters == null || filters.isEmpty()) {
            return true;
        }
        if (filters.containsKey("platforms")) {
            Object platforms = filters.get("platforms");
            if (platforms instanceof List<?> list && !list.isEmpty() && list.stream().noneMatch(value -> samePlatform(item.platform(), String.valueOf(value)))) {
                return false;
            }
        }
        if (filters.containsKey("maxPrice")) {
            BigDecimal maxPrice = number(filters.get("maxPrice"));
            if (maxPrice != null && amount(item.price()).compareTo(maxPrice) > 0) {
                return false;
            }
        }
        if (filters.containsKey("minPrice")) {
            BigDecimal minPrice = number(filters.get("minPrice"));
            if (minPrice != null && amount(item.price()).compareTo(minPrice) < 0) {
                return false;
            }
        }
        if (filters.containsKey("minRating")) {
            BigDecimal minRating = number(filters.get("minRating"));
            if (minRating != null && BigDecimal.valueOf(item.rating()).compareTo(minRating) < 0) {
                return false;
            }
        }
        if (Boolean.TRUE.equals(bool(filters.get("officialOnly"))) && !item.isOfficial()) {
            return false;
        }
        if (Boolean.TRUE.equals(bool(filters.get("selfOperatedOnly"))) && !item.isSelfOperated()) {
            return false;
        }
        if (filters.containsKey("color")) {
            String color = String.valueOf(filters.get("color"));
            String haystack = normalize(item.title() + " " + item.tags() + " " + productData(item.productId()).attributes());
            if (!contains(haystack, color)) {
                return false;
            }
        }
        MockCatalog.ProductData product = productData(item.productId());
        if (filters.containsKey("brand") && !contains(product.brand() + " " + item.title(), String.valueOf(filters.get("brand")))) {
            return false;
        }
        if (filters.containsKey("category") && !contains(product.category() + " " + item.title(), String.valueOf(filters.get("category")))) {
            return false;
        }
        return true;
    }

    private Comparator<ScoredProduct> comparatorFor(String sortBy) {
        String normalized = normalizeSort(sortBy);
        Comparator<ScoredProduct> comprehensive = Comparator
                .comparingDouble(ScoredProduct::score).reversed()
                .thenComparing(Comparator.comparing((ScoredProduct item) -> item.product().isOfficial()).reversed())
                .thenComparing(Comparator.comparingDouble((ScoredProduct item) -> item.product().rating()).reversed())
                .thenComparing(item -> amount(item.product().price()));
        return switch (normalized) {
            case "price_asc" -> Comparator.comparing(item -> amount(item.product().price()));
            case "sales_desc" -> Comparator.comparingInt((ScoredProduct item) -> item.product().salesVolume()).reversed()
                    .thenComparing(comprehensive);
            case "rating_desc" -> Comparator.comparingDouble((ScoredProduct item) -> item.product().rating()).reversed()
                    .thenComparing(comprehensive);
            default -> comprehensive;
        };
    }

    private List<PlatformStats> platformStats(List<SearchTaskItemDto> items) {
        return items.stream()
                .collect(Collectors.groupingBy(SearchTaskItemDto::platform, LinkedHashMap::new, Collectors.toList()))
                .entrySet().stream()
                .map(entry -> {
                    List<SearchTaskItemDto> group = entry.getValue();
                    BigDecimal min = group.stream().map(item -> amount(item.price())).min(BigDecimal::compareTo).orElse(BigDecimal.ZERO);
                    BigDecimal sum = group.stream().map(item -> amount(item.price())).reduce(BigDecimal.ZERO, BigDecimal::add);
                    BigDecimal avg = group.isEmpty() ? BigDecimal.ZERO : sum.divide(BigDecimal.valueOf(group.size()), 2, RoundingMode.HALF_UP);
                    return new PlatformStats(entry.getKey(), money(min), money(avg), group.size());
                })
                .toList();
    }

    private List<SuggestionCard> suggestionCards(String category, Map<String, Object> attributes, Map<String, Object> filters) {
        List<SuggestionCard> cards = new ArrayList<>();
        cards.add(new SuggestionCard("low-price", "sort", "查看同款低价", Map.of("sortBy", "price_asc"), 10));
        cards.add(new SuggestionCard("official-only", "official", "只看官方旗舰店", Map.of("officialOnly", true), 20));
        cards.add(new SuggestionCard("self-operated", "filter", "只看平台自营", Map.of("selfOperatedOnly", true), 22));
        cards.add(new SuggestionCard("high-rating", "filter", "评价 4.8 分以上", Map.of("minRating", 4.8, "sortBy", "rating_desc"), 30));
        cards.add(new SuggestionCard("history-price", "price_history", "查看历史价格走势", Map.of("action", "openPriceHistory"), 40));
        if (category != null && !category.isBlank()) {
            cards.add(new SuggestionCard("similar-style", "similar", "相似" + category + "推荐", Map.of("category", category), 50));
        }
        Object color = attributes == null ? null : attributes.get("color");
        if (color != null && !filters.containsKey("color")) {
            cards.add(new SuggestionCard("same-color", "filter", "筛选：" + color, Map.of("color", color), 25));
        }
        return cards.stream().sorted(Comparator.comparingInt(SuggestionCard::priority)).toList();
    }

    private RefineParseResult parseFilters(String text, Map<String, Object> existingFilters) {
        if (isBlank(text)) {
            return new RefineParseResult(Map.of(), "none", false, List.of());
        }
        return refineProvider.parse(text, existingFilters == null ? Map.of() : existingFilters);
    }

    private SearchTaskItemDto toSearchTaskItem(MockCatalog.PlatformProductData product, double matchScore, RecognitionRecord recognition, Map<String, Object> filters) {
        return new SearchTaskItemDto(
                product.platformProductId(),
                product.productId(),
                product.platform(),
                product.title(),
                product.imageUrl(),
                product.price(),
                product.originalPrice(),
                product.url(),
                product.shopName(),
                product.tags() == null ? List.of() : product.tags(),
                product.salesVolume(),
                product.rating(),
                product.isOfficial(),
                product.isSelfOperated(),
                round(matchScore),
                matchReasons(product, recognition, filters),
                normalizeSourceType(product.sourceType()),
                OffsetDateTime.now()
        );
    }

    private MockCatalog.ProductData productData(long productId) {
        return officialProductSource.product(productId)
                .orElseGet(() -> catalog.product(productId));
    }

    private MockCatalog.PlatformProductData platformProductData(long platformProductId) {
        return officialProductSource.platformProduct(platformProductId)
                .orElseGet(() -> catalog.platformProduct(platformProductId));
    }

    private Optional<MockCatalog.PriceHistoryData> priceHistoryData(long platformProductId) {
        Optional<MockCatalog.PriceHistoryData> official = officialProductSource.priceHistory(platformProductId);
        return official.isPresent() ? official : catalog.priceHistory(platformProductId);
    }

    private Optional<MockCatalog.ReviewSummaryData> reviewSummaryData(long platformProductId) {
        Optional<MockCatalog.ReviewSummaryData> official = officialProductSource.reviewSummary(platformProductId);
        return official.isPresent() ? official : catalog.reviewSummary(platformProductId);
    }

    private ProductDto toProductDto(MockCatalog.ProductData product) {
        return new ProductDto(
                product.productId(),
                product.name(),
                product.category(),
                product.brand(),
                product.model(),
                product.attributes(),
                OffsetDateTime.now()
        );
    }

    private PlatformProductDto toPlatformProductDto(MockCatalog.PlatformProductData product) {
        return new PlatformProductDto(
                product.platformProductId(),
                product.productId(),
                product.platform(),
                product.title(),
                product.imageUrl(),
                product.price(),
                product.originalPrice(),
                product.url(),
                product.shopName(),
                product.tags() == null ? List.of() : product.tags(),
                product.salesVolume(),
                product.rating(),
                product.isOfficial(),
                product.isSelfOperated(),
                normalizeSourceType(product.sourceType()),
                OffsetDateTime.now()
        );
    }

    private ReviewSummaryDto toReviewSummaryDto(MockCatalog.ReviewSummaryData summary) {
        return new ReviewSummaryDto(
                summary.platformProductId(),
                summary.rating(),
                summary.reviewCount(),
                summary.positiveTags() == null ? List.of() : summary.positiveTags(),
                summary.riskTags() == null ? List.of() : summary.riskTags(),
                summary.riskScore(),
                summary.summary()
        );
    }

    private SearchTaskDto toSearchTaskDto(SearchTaskRecord task) {
        RecognitionDto recognition = task.recognitionId == null ? null : toRecognitionDto(recognitions.get(task.recognitionId));
        return new SearchTaskDto(task.id, task.status, task.query, task.sourceType, task.filters, recognition, task.items, task.suggestionCards, task.platformStats, task.createdAt);
    }

    private RecognitionDto toRecognitionDto(RecognitionRecord record) {
        return new RecognitionDto(record.id, record.imageId, record.category, record.brand, record.model, record.keywords, record.attributes, record.suggestionCards, record.confidence, record.aiProvider, record.fallbackUsed, record.explanation, record.notices, record.status, record.createdAt);
    }

    private FavoriteDto toFavoriteDto(FavoriteRecord record) {
        MockCatalog.PlatformProductData product = platformProductData(record.platformProductId);
        return new FavoriteDto(record.id, record.platformProductId, product.platform(), product.title(), product.price(), record.note, record.createdAt);
    }

    private PriceAlertDto toPriceAlertDto(PriceAlertRecord record) {
        MockCatalog.PlatformProductData product = platformProductData(record.platformProductId);
        return new PriceAlertDto(record.id, record.platformProductId, product.title(), product.price(), record.targetPrice, record.enabled, record.createdAt, record.updatedAt);
    }

    private List<String> matchReasons(MockCatalog.PlatformProductData platformProduct, RecognitionRecord recognition, Map<String, Object> filters) {
        MockCatalog.ProductData product = productData(platformProduct.productId());
        List<String> reasons = new ArrayList<>();
        if (recognition != null) {
            if (contains(product.category(), recognition.category) || contains(platformProduct.title(), recognition.category)) {
                reasons.add("同类目：" + recognition.category);
            }
            if (!isBlank(recognition.brand) && contains(product.brand() + " " + platformProduct.title(), recognition.brand)) {
                reasons.add("品牌接近：" + recognition.brand);
            }
            Object color = recognition.attributes.get("color");
            if (color != null && contains(platformProduct.title() + " " + platformProduct.tags() + " " + product.attributes(), String.valueOf(color))) {
                reasons.add("颜色匹配：" + color);
            }
        }
        if (filters != null) {
            if (filters.containsKey("maxPrice")) {
                reasons.add("满足价格上限 ¥" + filters.get("maxPrice"));
            }
            if (filters.containsKey("minRating")) {
                reasons.add("评分 " + platformProduct.rating() + "，满足评价筛选");
            }
            if (Boolean.TRUE.equals(bool(filters.get("officialOnly"))) && platformProduct.isOfficial()) {
                reasons.add("官方旗舰店渠道");
            }
            if (Boolean.TRUE.equals(bool(filters.get("selfOperatedOnly"))) && platformProduct.isSelfOperated()) {
                reasons.add("平台自营渠道");
            }
        }
        if (platformProduct.tags() != null && !platformProduct.tags().isEmpty()) {
            reasons.add("标签：" + String.join("、", platformProduct.tags().stream().limit(3).toList()));
        }
        if (reasons.isEmpty()) {
            reasons.add("基于标题、类目、价格和评价的综合匹配");
        }
        return reasons;
    }

    private double recommendationScore(SearchTaskItemDto item) {
        double priceScore = 1.0 / Math.max(1.0, amount(item.price()).doubleValue());
        return item.matchScore() * 0.55 + item.rating() * 0.08 + Math.log1p(item.salesVolume()) * 0.02 + priceScore + (item.isOfficial() ? 0.05 : 0) + (item.isSelfOperated() ? 0.05 : 0);
    }

    private List<RecommendationSignalDto> decisionSignals(SearchTaskItemDto item, ReviewSummaryDto review, PriceHistoryDto history) {
        int match = percent(item.matchScore() * 100);
        int price = priceSignal(item, history);
        int reputation = percent((item.rating() / 5.0) * 100 - review.riskScore() * 18);
        int channel = percent(62 + (item.isOfficial() ? 22 : 0) + (item.isSelfOperated() ? 16 : 0));
        int risk = percent(100 - review.riskScore() * 100);
        return List.of(
                new RecommendationSignalDto("match", "意图匹配", match, "标题、类目、属性和自然语言筛选的综合匹配度。"),
                new RecommendationSignalDto("price", "价格位置", price, "当前价相对 90 天历史低点/高点的位置，越接近低点越高。"),
                new RecommendationSignalDto("reputation", "口碑质量", reputation, "评分和评价风险摘要的综合口碑信号。"),
                new RecommendationSignalDto("channel", "渠道可信", channel, "官方旗舰店、自营等渠道标签提升可信度。"),
                new RecommendationSignalDto("risk", "风险控制", risk, "评价风险越少、风险分越低，该信号越高。")
        );
    }

    private CandidateDecision candidateDecision(SearchTaskItemDto item) {
        ReviewSummaryDto review = reviewSummary(item.platformProductId());
        PriceHistoryDto history = priceHistory(item.platformProductId(), 90);
        List<RecommendationSignalDto> signals = decisionSignals(item, review, history);
        int score = decisionScore(signals);
        return new CandidateDecision(
                item,
                review,
                history,
                signals,
                score,
                candidateStrengths(item, review, history, signals),
                candidateWeaknesses(item, review, history, signals)
        );
    }

    private List<RecommendationCandidateDto> candidateAnalyses(List<CandidateDecision> rankedCandidates) {
        List<RecommendationCandidateDto> analyses = new ArrayList<>();
        for (int index = 0; index < rankedCandidates.size(); index++) {
            CandidateDecision candidate = rankedCandidates.get(index);
            SearchTaskItemDto item = candidate.item();
            analyses.add(new RecommendationCandidateDto(
                    item.platformProductId(),
                    item.platform(),
                    item.title(),
                    item.price(),
                    index + 1,
                    candidate.decisionScore(),
                    candidateVerdict(index, candidate),
                    candidate.strengths(),
                    candidate.weaknesses()
            ));
        }
        return analyses;
    }

    private String recommendationSummary(RecommendationDto dto, SearchTaskRecord task) {
        RecommendedPlatformProductDto product = dto.recommendedPlatformProduct();
        return suggestionText(dto.suggestion()) + "：" + product.title()
                + "，决策分 " + dto.decisionScore()
                + "，来源搜索任务 " + task.id
                + "，候选 " + dto.candidateAnalyses().size() + " 个。";
    }

    private String recommendationMarkdown(RecommendationDto dto, SearchTaskRecord task, String summary) {
        StringBuilder report = new StringBuilder();
        report.append("# 购物决策证据报告 #").append(dto.recommendationId()).append("\n\n");
        report.append("> ").append(summary).append("\n\n");
        report.append("## 任务上下文\n\n");
        report.append("- 搜索任务：").append(task.id).append("\n");
        report.append("- 数据源：").append(sourceTypeText(task.sourceType)).append("\n");
        report.append("- 用户需求：").append(fallbackText(task.query, "未提供")).append("\n");
        report.append("- 生成时间：").append(dto.createdAt()).append("\n\n");

        RecommendedPlatformProductDto product = dto.recommendedPlatformProduct();
        report.append("## 推荐结论\n\n");
        report.append("- 建议：").append(suggestionText(dto.suggestion())).append("\n");
        report.append("- 推荐商品：").append(product.title()).append("\n");
        report.append("- 平台：").append(product.platform()).append("\n");
        report.append("- 当前价：").append(product.price().amount()).append(" ").append(product.price().currency()).append("\n");
        report.append("- 匹配分：").append(formatDouble(product.matchScore())).append("\n");
        report.append("- 决策分：").append(dto.decisionScore()).append("/100\n\n");

        report.append("## 五类决策信号\n\n");
        for (RecommendationSignalDto signal : dto.decisionSignals()) {
            report.append("- ").append(signal.label()).append("：").append(signal.score()).append("/100。")
                    .append(signal.explanation()).append("\n");
        }
        report.append("\n## 六步决策轨迹\n\n");
        for (RecommendationTraceStepDto step : dto.decisionTrace()) {
            report.append("- ").append(step.label()).append("（").append(step.status()).append("，")
                    .append(step.confidence()).append("/100）：")
                    .append(step.observation()).append("\n");
        }
        report.append("\n## 候选胜因/败因矩阵\n\n");
        for (RecommendationCandidateDto candidate : dto.candidateAnalyses()) {
            report.append("### #").append(candidate.rank()).append(" ")
                    .append(verdictText(candidate.verdict())).append("：")
                    .append(candidate.title()).append("\n\n");
            report.append("- 平台：").append(candidate.platform()).append("\n");
            report.append("- 当前价：").append(candidate.price().amount()).append(" ").append(candidate.price().currency()).append("\n");
            report.append("- 决策分：").append(candidate.decisionScore()).append("/100\n");
            report.append("- 胜因：").append(String.join("；", candidate.strengths())).append("\n");
            report.append("- 败因：").append(String.join("；", candidate.weaknesses())).append("\n\n");
        }
        report.append("## 推荐理由\n\n");
        for (String reason : dto.reasons()) {
            report.append("- ").append(reason).append("\n");
        }
        report.append("\n## 风险提示\n\n");
        if (dto.risks().isEmpty()) {
            report.append("- 未发现明确高频风险。\n");
        } else {
            for (String risk : dto.risks()) {
                report.append("- ").append(risk).append("\n");
            }
        }
        report.append("\n## Evidence\n\n");
        for (RecommendationEvidenceDto evidence : dto.evidence()) {
            report.append("- [").append(evidence.type()).append("] 商品 ")
                    .append(evidence.platformProductId()).append("：")
                    .append(evidence.content()).append("\n");
        }
        report.append("\n## 合规边界\n\n");
        report.append("- 本报告中的价格、评分、评价摘要和历史价格来自服务端数据源。\n");
        report.append("- LLM 不直接生成商品事实；推荐结论由服务端证据和规则计算得到。\n");
        report.append("- 默认演示数据集来自本地 mock/sample dataset，不代表真实实时价格。\n");
        return report.toString();
    }

    private String verdictText(String verdict) {
        return switch (verdict == null ? "" : verdict) {
            case "winner" -> "胜出";
            case "runner_up" -> "备选";
            case "watch" -> "观察";
            case "rejected" -> "暂不推荐";
            default -> "候选";
        };
    }

    private List<String> candidateStrengths(SearchTaskItemDto item, ReviewSummaryDto review, PriceHistoryDto history, List<RecommendationSignalDto> signals) {
        List<String> strengths = new ArrayList<>();
        if (signalScore(signals, "match") >= 80) {
            strengths.add("意图匹配高");
        }
        if (signalScore(signals, "price") >= 82) {
            strengths.add("接近 90 天价格低位");
        }
        if (signalScore(signals, "reputation") >= 82) {
            strengths.add("口碑评分稳定");
        }
        if (signalScore(signals, "channel") >= 80) {
            strengths.add(item.isOfficial() && item.isSelfOperated() ? "官方/自营双标签" : "渠道可信度较高");
        }
        if (signalScore(signals, "risk") >= 82) {
            strengths.add("评价风险低");
        }
        if ("low".equals(history.trend())) {
            strengths.add("价格趋势接近低位");
        }
        if (review.positiveTags() != null && !review.positiveTags().isEmpty()) {
            strengths.add("评价亮点：" + String.join("、", review.positiveTags().stream().limit(2).toList()));
        }
        if (strengths.isEmpty()) {
            strengths.add("综合表现均衡");
        }
        return strengths.stream().limit(4).toList();
    }

    private List<String> candidateWeaknesses(SearchTaskItemDto item, ReviewSummaryDto review, PriceHistoryDto history, List<RecommendationSignalDto> signals) {
        List<String> weaknesses = new ArrayList<>();
        if (signalScore(signals, "match") < 72) {
            weaknesses.add("意图匹配弱于首选");
        }
        if (signalScore(signals, "price") < 72) {
            weaknesses.add("当前价距离历史低位偏远");
        }
        if (signalScore(signals, "reputation") < 76) {
            weaknesses.add("口碑信号不够稳定");
        }
        if (signalScore(signals, "channel") < 76) {
            weaknesses.add("缺少官方或自营确定性");
        }
        if (signalScore(signals, "risk") < 72) {
            weaknesses.add("评价风险需关注");
        }
        if ("high".equals(history.trend())) {
            weaknesses.add("历史价格处于高位");
        }
        if (review.riskTags() != null && !review.riskTags().isEmpty()) {
            weaknesses.add("风险标签：" + String.join("、", review.riskTags().stream().limit(2).toList()));
        }
        if (weaknesses.isEmpty()) {
            weaknesses.add(item.isOfficial() || item.isSelfOperated() ? "暂无明显短板" : "渠道背书略弱");
        }
        return weaknesses.stream().limit(4).toList();
    }

    private String candidateVerdict(int index, CandidateDecision candidate) {
        if (index == 0) {
            return "winner";
        }
        if (candidate.decisionScore() >= 82) {
            return "runner_up";
        }
        if (candidate.decisionScore() >= 70) {
            return "watch";
        }
        return "rejected";
    }

    private List<RecommendationTraceStepDto> decisionTrace(
            SearchTaskRecord task,
            List<SearchTaskItemDto> candidates,
            SearchTaskItemDto best,
            ReviewSummaryDto review,
            PriceHistoryDto history,
            List<RecommendationSignalDto> decisionSignals,
            String suggestion,
            int decisionScore
    ) {
        RecognitionRecord recognition = task.recognitionId == null ? null : recognitions.get(task.recognitionId);
        Map<String, Object> filters = task.filters == null ? Map.of() : task.filters;
        int intentConfidence = recognition == null ? 72 : percent(recognition.confidence * 100);
        String intentObservation = recognition == null
                ? "使用文本需求：" + compactText(task.query, 30)
                : "识别为 " + recognition.category + "，品牌 " + fallbackText(recognition.brand, "未知") + "，模型 " + fallbackText(recognition.model, "未识别") + "。";
        String filterObservation = filterSummary(filters);
        String sourceLabel = sourceTypeText(task.sourceType);
        String riskObservation = review.riskTags() == null || review.riskTags().isEmpty()
                ? "评价摘要未发现明确高频风险，风险分 " + formatDouble(review.riskScore()) + "。"
                : "评价风险：" + String.join("、", review.riskTags()) + "，风险分 " + formatDouble(review.riskScore()) + "。";
        return List.of(
                new RecommendationTraceStepDto("intent", "识别意图", "done", intentConfidence, intentObservation),
                new RecommendationTraceStepDto("constraints", "约束解析", filters.isEmpty() ? "watch" : "done", Math.max(70, signalScore(decisionSignals, "match")), filterObservation),
                new RecommendationTraceStepDto("retrieval", "商品召回", "done", percent(Math.min(100, candidates.size() * 18 + 42)), sourceLabel + "返回 " + candidates.size() + " 个候选，覆盖 " + platformStats(candidates).size() + " 个平台。"),
                new RecommendationTraceStepDto("market", "价格时机", signalScore(decisionSignals, "price") >= 70 ? "done" : "watch", signalScore(decisionSignals, "price"), "当前价 " + best.price().amount() + " CNY，90 天低点 " + history.lowestPrice().amount() + " CNY，趋势 " + trendText(history.trend()) + "。"),
                new RecommendationTraceStepDto("risk", "风险审计", signalScore(decisionSignals, "risk") >= 65 ? "done" : "watch", signalScore(decisionSignals, "risk"), riskObservation),
                new RecommendationTraceStepDto("decision", "最终建议", "buy".equals(suggestion) ? "done" : "watch", decisionScore, suggestionText(suggestion) + "，综合决策分 " + decisionScore + "。")
        );
    }

    private int priceSignal(SearchTaskItemDto item, PriceHistoryDto history) {
        BigDecimal current = amount(item.price());
        BigDecimal lowest = amount(history.lowestPrice());
        BigDecimal highest = amount(history.highestPrice());
        BigDecimal span = highest.subtract(lowest);
        int score;
        if (span.compareTo(BigDecimal.ZERO) <= 0) {
            score = 72;
        } else if (current.compareTo(lowest.multiply(new BigDecimal("1.05"))) <= 0) {
            score = 96;
        } else if (current.compareTo(lowest.multiply(new BigDecimal("1.12"))) <= 0) {
            score = 84;
        } else if (current.compareTo(highest.multiply(new BigDecimal("0.95"))) >= 0) {
            score = 46;
        } else {
            BigDecimal position = current.subtract(lowest).divide(span, 4, RoundingMode.HALF_UP);
            score = percent(100 - position.doubleValue() * 48);
        }
        if ("low".equals(history.trend())) {
            score += 4;
        } else if ("high".equals(history.trend())) {
            score -= 8;
        }
        return percent(score);
    }

    private int decisionScore(List<RecommendationSignalDto> signals) {
        return percent(
                signalScore(signals, "match") * 0.28
                        + signalScore(signals, "price") * 0.24
                        + signalScore(signals, "reputation") * 0.18
                        + signalScore(signals, "channel") * 0.14
                        + signalScore(signals, "risk") * 0.16
        );
    }

    private int signalScore(List<RecommendationSignalDto> signals, String key) {
        return signals.stream()
                .filter(signal -> key.equals(signal.key()))
                .findFirst()
                .map(RecommendationSignalDto::score)
                .orElse(0);
    }

    private SearchTaskRecord searchTaskForUser(long userId, long searchTaskId) {
        SearchTaskRecord record = searchTasks.get(searchTaskId);
        if (record == null || record.userId != userId) {
            throw ApiException.notFound(40403, "search task not found");
        }
        return record;
    }

    private RecognitionRecord recognitionForUser(long userId, long recognitionId) {
        RecognitionRecord record = recognitions.get(recognitionId);
        if (record == null || record.userId != userId) {
            throw ApiException.notFound(40402, "recognition not found");
        }
        return record;
    }

    private ImageRecord imageForUser(long userId, long imageId) {
        ImageRecord record = images.get(imageId);
        if (record == null || record.userId() != userId || record.deleted()) {
            throw ApiException.notFound(40401, "image not found");
        }
        return record;
    }

    private PriceAlertRecord priceAlertForUser(long userId, long priceAlertId) {
        PriceAlertRecord record = priceAlerts.get(priceAlertId);
        if (record == null || record.userId != userId) {
            throw ApiException.notFound(40407, "price alert not found");
        }
        return record;
    }

    private AuthPayload issueAuth(UserAccount user) {
        String accessToken = jwtService.createAccessToken(user.id());
        String refreshToken = randomToken();
        String refreshTokenHash = hashToken(refreshToken);
        refreshSessions.put(refreshTokenHash, user.id());
        stateRepository.saveRefreshSession(refreshTokenHash, user.id());
        return new AuthPayload(accessToken, refreshToken, jwtService.accessTokenSeconds(), toUserDto(user));
    }

    private UserDto toUserDto(UserAccount user) {
        return new UserDto(user.id(), user.username(), user.nickname(), user.avatarUrl(), user.status());
    }

    private ImageDto toImageDto(ImageRecord record) {
        return new ImageDto(record.imageId(), record.imageUrl(), record.contentType(), record.size(), record.createdAt());
    }

    private ImagePayload imagePayload(ImageRecord record) {
        byte[] bytes = new byte[0];
        String filename = record.imageUrl();
        if (record.imageUrl() != null && record.imageUrl().startsWith("/uploads/")) {
            filename = record.imageUrl().substring("/uploads/".length());
            try {
                bytes = Files.readAllBytes(resolveUploadsPath().resolve(filename));
            } catch (IOException ignored) {
                bytes = new byte[0];
            }
        }
        return new ImagePayload(record.imageId(), record.imageUrl(), record.contentType(), bytes, filename);
    }

    private Path resolveUploadsPath() {
        Path configured = Path.of(uploadDir);
        if (configured.isAbsolute()) {
            return configured;
        }
        Path cwd = Path.of("").toAbsolutePath();
        if (Files.exists(cwd.resolve(configured)) || Files.exists(cwd.resolve("backend"))) {
            return cwd.resolve(configured);
        }
        return cwd.resolve("..").resolve(configured).normalize();
    }

    private String randomToken() {
        byte[] bytes = new byte[32];
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private String hashToken(String token) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return Base64.getUrlEncoder().withoutPadding().encodeToString(digest.digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot hash token", ex);
        }
    }

    private String extension(String originalName, String contentType) {
        if (originalName != null && originalName.contains(".")) {
            return originalName.substring(originalName.lastIndexOf('.')).replaceAll("[^A-Za-z0-9.]", "");
        }
        if ("image/png".equals(contentType)) {
            return ".png";
        }
        if ("image/webp".equals(contentType)) {
            return ".webp";
        }
        return ".jpg";
    }

    private String basename(String originalName) {
        if (originalName == null || originalName.isBlank()) {
            return "upload";
        }
        String cleaned = originalName;
        int dot = cleaned.lastIndexOf('.');
        if (dot > 0) {
            cleaned = cleaned.substring(0, dot);
        }
        cleaned = cleaned.replaceAll("[^A-Za-z0-9_-]", "-");
        return cleaned.isBlank() ? "upload" : cleaned;
    }

    private boolean looksLikeImage(String originalName) {
        if (originalName == null) {
            return false;
        }
        String lower = originalName.toLowerCase(Locale.ROOT);
        return lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".png") || lower.endsWith(".webp");
    }

    private String normalizeSourceType(String sourceType) {
        String normalized = sourceType == null || sourceType.isBlank() ? "mock" : sourceType.toLowerCase(Locale.ROOT);
        if (!SOURCE_TYPES.contains(normalized)) {
            throw ApiException.badRequest("sourceType invalid");
        }
        return normalized;
    }

    private String normalizeSort(String sortBy) {
        if (isBlank(sortBy)) {
            return "comprehensive";
        }
        String normalized = sortBy.toLowerCase(Locale.ROOT);
        return SORT_MODES.contains(normalized) ? normalized : "comprehensive";
    }

    private String requireText(String value, String field) {
        if (isBlank(value)) {
            throw ApiException.badRequest(field + " is required");
        }
        return value.trim();
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private String normalize(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (!isBlank(value)) {
                return value;
            }
        }
        return null;
    }

    private boolean contains(String value, String keyword) {
        return !isBlank(keyword) && normalize(value).contains(normalize(keyword));
    }

    private boolean samePlatform(String left, String right) {
        return normalizePlatform(left).equals(normalizePlatform(right));
    }

    private String normalizePlatform(String value) {
        String normalized = normalize(value).replace("平台", "").replace("商城", "");
        return switch (normalized) {
            case "pdd", "拼多多", "多多进宝" -> "pdd";
            case "jd", "jingdong", "京东", "京东自营" -> "jd";
            case "taobao", "淘宝" -> "taobao";
            case "tmall", "天猫" -> "tmall";
            default -> normalized;
        };
    }

    private <T> List<T> safeList(List<T> value) {
        return value == null ? List.of() : value;
    }

    private Map<String, Object> safeMap(Map<String, Object> value) {
        return value == null ? new LinkedHashMap<>() : new LinkedHashMap<>(value);
    }

    private <T> PageData<T> page(List<T> all, int page, int pageSize) {
        int safePage = Math.max(1, page);
        int safeSize = Math.max(1, Math.min(100, pageSize));
        int from = Math.min(all.size(), (safePage - 1) * safeSize);
        int to = Math.min(all.size(), from + safeSize);
        return new PageData<>(all.subList(from, to), safePage, safeSize, all.size());
    }

    private BigDecimal number(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return BigDecimal.valueOf(number.doubleValue());
        }
        if (value instanceof Money money) {
            return new BigDecimal(money.amount());
        }
        if (value instanceof Map<?, ?> map && map.containsKey("amount")) {
            return number(map.get("amount"));
        }
        String text = String.valueOf(value).replace("CNY", "").replace("元", "").trim();
        if (text.isBlank()) {
            return null;
        }
        return new BigDecimal(text);
    }

    private BigDecimal amount(Money money) {
        return new BigDecimal(money.amount());
    }

    private Boolean bool(Object value) {
        if (value instanceof Boolean bool) {
            return bool;
        }
        if (value == null) {
            return false;
        }
        return Boolean.parseBoolean(String.valueOf(value));
    }

    private Money money(BigDecimal amount) {
        return new Money(formatMoney(amount), "CNY");
    }

    private String formatMoney(BigDecimal amount) {
        return amount.setScale(2, RoundingMode.HALF_UP).toPlainString();
    }

    private double round(double value) {
        return BigDecimal.valueOf(value).setScale(2, RoundingMode.HALF_UP).doubleValue();
    }

    private int percent(double value) {
        return Math.max(0, Math.min(100, (int) Math.round(value)));
    }

    private String formatDouble(double value) {
        return BigDecimal.valueOf(value).setScale(2, RoundingMode.HALF_UP).toPlainString();
    }

    private String fallbackText(String value, String fallback) {
        return isBlank(value) ? fallback : value;
    }

    private String compactText(String value, int maxLength) {
        String text = fallbackText(value, "未提供").trim();
        if (text.length() <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength) + "...";
    }

    private String filterSummary(Map<String, Object> filters) {
        List<String> parts = new ArrayList<>();
        if (filters.containsKey("minPrice") || filters.containsKey("maxPrice")) {
            String min = filters.containsKey("minPrice") ? String.valueOf(filters.get("minPrice")) : "不限";
            String max = filters.containsKey("maxPrice") ? String.valueOf(filters.get("maxPrice")) : "不限";
            parts.add("预算 " + min + "-" + max);
        }
        if (Boolean.TRUE.equals(bool(filters.get("officialOnly")))) {
            parts.add("只看官方");
        }
        if (Boolean.TRUE.equals(bool(filters.get("selfOperatedOnly")))) {
            parts.add("只看自营");
        }
        if (filters.containsKey("minRating")) {
            parts.add("评分不低于 " + filters.get("minRating"));
        }
        if (filters.containsKey("color")) {
            parts.add("颜色 " + filters.get("color"));
        }
        if (filters.containsKey("sortBy")) {
            parts.add("排序 " + sortText(String.valueOf(filters.get("sortBy"))));
        }
        if (parts.isEmpty()) {
            return "未解析到额外筛选条件，按识别意图和综合排序检索。";
        }
        return "解析出 " + String.join("、", parts) + "。";
    }

    private String sortText(String sortBy) {
        return switch (sortBy) {
            case "price_asc" -> "低价优先";
            case "sales_desc" -> "销量优先";
            case "rating_desc" -> "好评优先";
            default -> "综合";
        };
    }

    private String trendText(String trend) {
        String normalized = fallbackText(trend, "unknown");
        return switch (normalized) {
            case "low" -> "接近低位";
            case "high" -> "接近高位";
            case "flat" -> "平稳";
            default -> normalized;
        };
    }

    private String suggestionText(String suggestion) {
        String normalized = fallbackText(suggestion, "compare");
        return switch (normalized) {
            case "buy" -> "建议购买";
            case "wait" -> "建议观望";
            case "avoid" -> "建议避开";
            default -> "建议继续对比";
        };
    }

    private String sourceTypeText(String sourceType) {
        return switch (fallbackText(sourceType, "mock")) {
            case "official_api" -> "官方 API";
            case "sample_dataset" -> "授权样例数据";
            default -> "演示数据集";
        };
    }

    public record UserAccount(long id, String username, String passwordHash, String nickname, String avatarUrl, String status) {
    }

    private record ImageRecord(long imageId, long userId, String imageUrl, String contentType, long size, OffsetDateTime createdAt, boolean deleted) {
    }

    private static final class RecognitionRecord {
        private final long id;
        private final long userId;
        private final long imageId;
        private String category;
        private String brand;
        private String model;
        private final List<String> keywords;
        private Map<String, Object> attributes;
        private List<SuggestionCard> suggestionCards = List.of();
        private final double confidence;
        private final String aiProvider;
        private final boolean fallbackUsed;
        private final String explanation;
        private final List<String> notices;
        private final String status;
        private final OffsetDateTime createdAt;

        private RecognitionRecord(long id, long userId, long imageId, String category, String brand, String model, List<String> keywords, Map<String, Object> attributes, double confidence, String aiProvider, boolean fallbackUsed, String explanation, List<String> notices, String status, OffsetDateTime createdAt) {
            this.id = id;
            this.userId = userId;
            this.imageId = imageId;
            this.category = category;
            this.brand = brand;
            this.model = model;
            this.keywords = keywords;
            this.attributes = attributes;
            this.confidence = confidence;
            this.aiProvider = aiProvider;
            this.fallbackUsed = fallbackUsed;
            this.explanation = explanation;
            this.notices = notices;
            this.status = status;
            this.createdAt = createdAt;
        }
    }

    private static final class SearchTaskRecord {
        private final long id;
        private final long userId;
        private final Long recognitionId;
        private final String query;
        private final String sourceType;
        private Map<String, Object> filters;
        private final String status;
        private List<SearchTaskItemDto> items;
        private List<SuggestionCard> suggestionCards;
        private List<PlatformStats> platformStats;
        private final OffsetDateTime createdAt;

        private SearchTaskRecord(long id, long userId, Long recognitionId, String query, String sourceType, Map<String, Object> filters, String status, List<SearchTaskItemDto> items, List<SuggestionCard> suggestionCards, List<PlatformStats> platformStats, OffsetDateTime createdAt) {
            this.id = id;
            this.userId = userId;
            this.recognitionId = recognitionId;
            this.query = query;
            this.sourceType = sourceType;
            this.filters = filters;
            this.status = status;
            this.items = items;
            this.suggestionCards = suggestionCards;
            this.platformStats = platformStats;
            this.createdAt = createdAt;
        }
    }

    private record ScoredProduct(MockCatalog.PlatformProductData product, double score) {
    }

    private record CandidateDecision(
            SearchTaskItemDto item,
            ReviewSummaryDto review,
            PriceHistoryDto history,
            List<RecommendationSignalDto> signals,
            int decisionScore,
            List<String> strengths,
            List<String> weaknesses
    ) {
    }

    private record ComparisonRecord(long id, long userId, ComparisonDto dto) {
    }

    private static final class FavoriteRecord {
        private final long id;
        private final long userId;
        private final long platformProductId;
        private final String note;
        private final OffsetDateTime createdAt;

        private FavoriteRecord(long id, long userId, long platformProductId, String note, OffsetDateTime createdAt) {
            this.id = id;
            this.userId = userId;
            this.platformProductId = platformProductId;
            this.note = note;
            this.createdAt = createdAt;
        }
    }

    private static final class PriceAlertRecord {
        private final long id;
        private final long userId;
        private final long platformProductId;
        private final Money targetPrice;
        private final boolean enabled;
        private final OffsetDateTime createdAt;
        private final OffsetDateTime updatedAt;

        private PriceAlertRecord(long id, long userId, long platformProductId, Money targetPrice, boolean enabled, OffsetDateTime createdAt, OffsetDateTime updatedAt) {
            this.id = id;
            this.userId = userId;
            this.platformProductId = platformProductId;
            this.targetPrice = targetPrice;
            this.enabled = enabled;
            this.createdAt = createdAt;
            this.updatedAt = updatedAt;
        }
    }
}
