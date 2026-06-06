package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class MockProductSourceProvider implements ProductSourceProvider {

    private final RecommendationScorer scorer;

    public MockProductSourceProvider(RecommendationScorer scorer) {
        this.scorer = scorer;
    }

    @Override
    public ProductSearchResult search(ProductSearchQuery query) {
        List<ProductOffer> all = new ArrayList<>();
        all.addAll(jdProducts(query));
        all.addAll(pddProducts(query));
        all.addAll(tbProducts(query));

        List<String> prefs = query.preferences() != null ? query.preferences() : List.of();
        Double maxPrice = query.maxPrice();
        List<ProductOffer> scored = all.stream()
                .map(p -> scorer.scoreProduct(p, prefs, maxPrice))
                .sorted((a, b) -> Double.compare(b.score(), a.score()))
                .toList();

        List<ProductOffer> filtered = maxPrice != null
                ? scored.stream().filter(p -> p.price() <= maxPrice).toList()
                : scored;

        // Color filter (after budget)
        String color = query.color();
        if (color != null && !color.isBlank()) {
            filtered = filtered.stream()
                    .filter(p -> p.title().contains(color)
                            || p.tags().stream().anyMatch(t -> t.contains(color)))
                    .toList();
        }

        Map<String, ProductSearchResult.PlatformStats> stats = new LinkedHashMap<>();
        for (String platform : List.of("京东-mock", "拼多多-mock", "淘宝-mock")) {
            List<ProductOffer> platformProducts = filtered.stream()
                    .filter(p -> p.platform().equals(platform))
                    .toList();
            if (!platformProducts.isEmpty()) {
                double lowest = platformProducts.stream()
                        .mapToDouble(ProductOffer::price).min().orElse(0);
                String highlight = switch (platform) {
                    case "京东-mock" -> "自营保障，物流快";
                    case "拼多多-mock" -> "价格优势明显";
                    case "淘宝-mock" -> "品类丰富，选择多";
                    default -> "";
                };
                stats.put(platform, new ProductSearchResult.PlatformStats(
                        platform, lowest, platformProducts.size(), highlight));
            }
        }

        ProductOffer topPick = filtered.isEmpty() ? null : filtered.get(0);
        return new ProductSearchResult(filtered, stats, topPick);
    }

    @Override
    public String sourceName() {
        return "mock";
    }

    // ── JD products ──────────────────────────────────────────────

    private List<ProductOffer> jdProducts(ProductSearchQuery query) {
        String kw = query.keyword();
        if (kw.contains("耳机")) {
            return List.of(
                    new ProductOffer("jd-101", "蓝牙降噪耳机 黑色 高音质", "京东-mock",
                            299.00, 499.00, "京东自营",
                            "", "", 4.9, 23000,
                            List.of("自营", "降噪"),
                            List.of(), 0),
                    new ProductOffer("jd-102", "入耳式耳机 白色 长续航", "京东-mock",
                            179.00, 259.00, "品牌旗舰店",
                            "", "", 4.7, 18000,
                            List.of("官方", "长续航", "入耳式"),
                            List.of(), 0),
                    new ProductOffer("jd-103", "头戴式降噪耳机 黑色 专业级", "京东-mock",
                            458.00, 599.00, "京东自营",
                            "", "", 4.8, 15000,
                            List.of("自营", "降噪", "头戴式"),
                            List.of(), 0),
                    new ProductOffer("jd-104", "运动蓝牙耳机 蓝色 防水", "京东-mock",
                            259.00, 349.00, "品牌专营店",
                            "", "", 4.5, 9000,
                            List.of("防水"),
                            List.of(), 0)
            );
        }
        if (kw.contains("吹风机")) {
            return List.of(
                    new ProductOffer("jd-201", "负离子护发吹风机 大功率 白色", "京东-mock",
                            199.00, 359.00, "京东自营",
                            "", "", 4.8, 15000,
                            List.of("自营", "负离子"),
                            List.of(), 0),
                    new ProductOffer("jd-202", "高速吹风机 静音设计 黑色", "京东-mock",
                            349.00, 499.00, "品牌旗舰店",
                            "", "", 4.9, 9800,
                            List.of("官方", "静音", "高速"),
                            List.of(), 0),
                    new ProductOffer("jd-203", "便携折叠吹风机 粉色", "京东-mock",
                            149.00, 259.00, "京东自营",
                            "", "", 4.6, 22000,
                            List.of("自营", "便携", "折叠"),
                            List.of(), 0),
                    new ProductOffer("jd-204", "大功率家用吹风机 白色", "京东-mock",
                            259.00, 359.00, "品牌专营店",
                            "", "", 4.5, 11000,
                            List.of(),
                            List.of(), 0)
            );
        }
        return List.of(
                new ProductOffer("jd-001", "品牌运动鞋 轻便透气 白色", "京东-mock",
                        299.00, 399.00, "京东自营",
                        "", "", 4.8, 12000,
                        List.of("自营", "透气", "通勤"),
                        List.of(), 0),
                new ProductOffer("jd-002", "官方旗舰减震训练运动鞋 黑色", "京东-mock",
                        389.00, 499.00, "官方旗舰店",
                        "", "", 4.9, 8500,
                        List.of("官方", "旗舰店", "减震", "跑步"),
                        List.of(), 0),
                new ProductOffer("jd-003", "经典复古运动鞋 灰白色", "京东-mock",
                        459.00, 559.00, "京东自营",
                        "", "", 4.7, 6200,
                        List.of("自营", "复古"),
                        List.of(), 0),
                new ProductOffer("jd-004", "透气网面跑步运动鞋 深蓝色", "京东-mock",
                        219.00, 299.00, "品牌专营店",
                        "", "", 4.4, 18000,
                        List.of("透气", "跑步"),
                        List.of(), 0)
        );
    }

    // ── PDD products ─────────────────────────────────────────────

    private List<ProductOffer> pddProducts(ProductSearchQuery query) {
        String kw = query.keyword();
        if (kw.contains("耳机")) {
            return List.of(
                    new ProductOffer("pdd-101", "爆款蓝牙耳机 高性价比 黑色", "拼多多-mock",
                            79.00, 199.00, "数码专营店",
                            "", "", 4.3, 92000,
                            List.of("爆款", "性价比"),
                            List.of(), 0),
                    new ProductOffer("pdd-102", "无线耳机 运动款 防水 白色", "拼多多-mock",
                            129.00, 189.00, "耳机专营店",
                            "", "", 4.2, 35000,
                            List.of("性价比", "防水"),
                            List.of(), 0),
                    new ProductOffer("pdd-103", "头戴式游戏耳机 黑色", "拼多多-mock",
                            239.00, 349.00, "数码专营店",
                            "", "", 4.4, 28000,
                            List.of("头戴式"),
                            List.of(), 0),
                    new ProductOffer("pdd-104", "降噪蓝牙耳机 长续航 白色", "拼多多-mock",
                            149.00, 229.00, "品牌折扣店",
                            "", "", 4.1, 56000,
                            List.of("降噪", "长续航"),
                            List.of(), 0)
            );
        }
        if (kw.contains("吹风机")) {
            return List.of(
                    new ProductOffer("pdd-201", "大功率吹风机 家用款 白色", "拼多多-mock",
                            59.00, 129.00, "家电专营店",
                            "", "", 4.3, 68000,
                            List.of("爆款", "性价比"),
                            List.of(), 0),
                    new ProductOffer("pdd-202", "负离子护发吹风机 粉色", "拼多多-mock",
                            89.00, 159.00, "品牌折扣店",
                            "", "", 4.1, 42000,
                            List.of("性价比", "负离子"),
                            List.of(), 0),
                    new ProductOffer("pdd-203", "便携迷你吹风机 白色", "拼多多-mock",
                            79.00, 139.00, "家电专营店",
                            "", "", 4.2, 35000,
                            List.of("便携", "性价比"),
                            List.of(), 0),
                    new ProductOffer("pdd-204", "静音高速吹风机 黑色", "拼多多-mock",
                            109.00, 199.00, "数码专营店",
                            "", "", 4.4, 52000,
                            List.of("静音", "高速", "性价比"),
                            List.of(), 0)
            );
        }
        return List.of(
                new ProductOffer("pdd-001", "爆款运动鞋 网面透气 白色", "拼多多-mock",
                        199.00, 299.00, "品牌专营店",
                        "", "", 4.5, 58000,
                        List.of("爆款", "透气"),
                        List.of(), 0),
                new ProductOffer("pdd-002", "轻便百搭运动鞋 米色", "拼多多-mock",
                        239.00, 329.00, "运动鞋专营店",
                        "", "", 4.3, 23000,
                        List.of("性价比"),
                        List.of(), 0),
                new ProductOffer("pdd-003", "夏季透气跑步运动鞋 黑色", "拼多多-mock",
                        169.00, 249.00, "品牌折扣店",
                        "", "", 4.2, 78000,
                        List.of("性价比", "跑步", "透气"),
                        List.of(), 0),
                new ProductOffer("pdd-004", "复古厚底运动鞋 白色", "拼多多-mock",
                        189.00, 269.00, "潮鞋专营店",
                        "", "", 4.4, 45000,
                        List.of("复古", "性价比"),
                        List.of(), 0)
        );
    }

    // ── TB products ──────────────────────────────────────────────

    private List<ProductOffer> tbProducts(ProductSearchQuery query) {
        String kw = query.keyword();
        if (kw.contains("耳机")) {
            return List.of(
                    new ProductOffer("tb-101", "新款降噪耳机 时尚设计 黑色", "淘宝-mock",
                            249.00, 399.00, "品牌官方店",
                            "", "", 4.6, 12000,
                            List.of("官方", "降噪"),
                            List.of(), 0),
                    new ProductOffer("tb-102", "复古头戴式耳机 经典黑", "淘宝-mock",
                            199.00, 299.00, "潮品集合店",
                            "", "", 4.5, 7800,
                            List.of("复古", "头戴式"),
                            List.of(), 0),
                    new ProductOffer("tb-103", "入耳式HiFi耳机 银色", "淘宝-mock",
                            359.00, 459.00, "品牌官方店",
                            "", "", 4.7, 8500,
                            List.of("官方", "入耳式"),
                            List.of(), 0),
                    new ProductOffer("tb-104", "运动防水蓝牙耳机 绿色", "淘宝-mock",
                            159.00, 249.00, "潮品集合店",
                            "", "", 4.3, 32000,
                            List.of("防水"),
                            List.of(), 0)
            );
        }
        if (kw.contains("吹风机")) {
            return List.of(
                    new ProductOffer("tb-201", "轻量吹风机 便携折叠 白色", "淘宝-mock",
                            129.00, 229.00, "品牌官方店",
                            "", "", 4.5, 22000,
                            List.of("官方", "便携", "折叠"),
                            List.of(), 0),
                    new ProductOffer("tb-202", "家用大功率吹风机 负离子护发", "淘宝-mock",
                            159.00, 269.00, "电器专营店",
                            "", "", 4.4, 16000,
                            List.of("负离子"),
                            List.of(), 0),
                    new ProductOffer("tb-203", "专业沙龙级吹风机 高速 黑色", "淘宝-mock",
                            299.00, 459.00, "品牌官方店",
                            "", "", 4.7, 12000,
                            List.of("官方", "高速"),
                            List.of(), 0),
                    new ProductOffer("tb-204", "迷你旅行吹风机 粉色", "淘宝-mock",
                            99.00, 169.00, "潮品集合店",
                            "", "", 4.2, 28000,
                            List.of("便携", "折叠"),
                            List.of(), 0)
            );
        }
        return List.of(
                new ProductOffer("tb-001", "春季新款运动鞋 百搭配色 白色", "淘宝-mock",
                        279.00, 359.00, "品牌官方店",
                        "", "", 4.7, 15000,
                        List.of("官方", "通勤"),
                        List.of(), 0),
                new ProductOffer("tb-002", "复古运动鞋 经典白色 通勤款", "淘宝-mock",
                        259.00, 339.00, "潮鞋集合店",
                        "", "", 4.6, 9800,
                        List.of("复古", "通勤"),
                        List.of(), 0),
                new ProductOffer("tb-003", "减震训练运动鞋 黑色", "淘宝-mock",
                        329.00, 429.00, "品牌官方店",
                        "", "", 4.8, 22000,
                        List.of("官方", "减震", "跑步"),
                        List.of(), 0),
                new ProductOffer("tb-004", "厚底增高运动鞋 粉色", "淘宝-mock",
                        219.00, 289.00, "潮品集合店",
                        "", "", 4.2, 31000,
                        List.of("通勤"),
                        List.of(), 0)
        );
    }
}
