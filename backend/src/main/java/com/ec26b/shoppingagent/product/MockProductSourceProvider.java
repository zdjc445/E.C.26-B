package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Comparator;
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
        UserPreference pref = new UserPreference(query.maxPrice(), query.color(),
                false, false, false, false, false,
                query.brand(), query.platforms(), query.sortBy(), query.minRating());

        List<ProductOffer> all = new ArrayList<>();
        all.addAll(jdProducts(query));
        all.addAll(pddProducts(query));
        all.addAll(tbProducts(query));

        List<String> prefs = query.preferences() != null ? query.preferences() : List.of();
        Double maxPrice = query.maxPrice();

        List<ProductOffer> scored = all.stream()
                .map(p -> scorer.scoreProduct(p, prefs, maxPrice, pref))
                .toList();

        // Filter: budget, color, brand, platforms, minRating
        List<ProductOffer> filtered = scored.stream()
                .filter(p -> maxPrice == null || p.price() <= maxPrice)
                .toList();

        String color = query.color();
        if (color != null && !color.isBlank()) {
            filtered = filtered.stream()
                    .filter(p -> p.title().contains(color)
                            || p.tags().stream().anyMatch(t -> t.contains(color)))
                    .toList();
        }

        String brand = query.brand();
        if (brand != null && !brand.isBlank()) {
            filtered = filtered.stream()
                    .filter(p -> brand.equals(p.brand())
                            || (p.title() != null && p.title().contains(brand)))
                    .toList();
        }

        List<String> platforms = query.platforms();
        if (platforms != null && !platforms.isEmpty()) {
            filtered = filtered.stream()
                    .filter(p -> platforms.contains(p.platform()))
                    .toList();
        }

        Double minRating = query.minRating();
        if (minRating != null) {
            filtered = filtered.stream()
                    .filter(p -> p.rating() >= minRating)
                    .toList();
        }

        // Sort
        String sortBy = query.sortBy();
        Comparator<ProductOffer> comparator = switch (sortBy == null ? "" : sortBy) {
            case "price_asc" -> Comparator.comparingDouble(ProductOffer::price);
            case "price_desc" -> Comparator.comparingDouble(ProductOffer::price).reversed();
            case "sales_desc" -> Comparator.comparingInt(ProductOffer::sales).reversed();
            case "rating_desc" -> Comparator.comparingDouble(ProductOffer::rating).reversed();
            default -> Comparator.comparingDouble(ProductOffer::score).reversed();
        };
        List<ProductOffer> sorted = new ArrayList<>(filtered);
        sorted.sort(comparator);

        Map<String, ProductSearchResult.PlatformStats> stats = new LinkedHashMap<>();
        for (String platform : List.of("京东-mock", "拼多多-mock", "淘宝-mock")) {
            List<ProductOffer> platformProducts = sorted.stream()
                    .filter(p -> p.platform().equals(platform))
                    .toList();
            if (!platformProducts.isEmpty()) {
                double lowest = platformProducts.stream()
                        .mapToDouble(ProductOffer::price).min().orElse(0);
                double avg = platformProducts.stream()
                        .mapToDouble(ProductOffer::price).average().orElse(0);
                String highlight = switch (platform) {
                    case "京东-mock" -> "自营保障，物流快";
                    case "拼多多-mock" -> "价格优势明显";
                    case "淘宝-mock" -> "品类丰富，选择多";
                    default -> "";
                };
                stats.put(platform, new ProductSearchResult.PlatformStats(
                        platform, lowest, Math.round(avg * 100.0) / 100.0,
                        platformProducts.size(), highlight));
            }
        }

        ProductOffer topPick = sorted.isEmpty() ? null : sorted.get(0);
        return new ProductSearchResult(sorted, stats, topPick);
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
                    p("jd-101", "索尼蓝牙降噪耳机 黑色 高音质", "京东-mock",
                            299.00, 499.00, "索尼京东自营",
                            4.9, 23000, List.of("自营", "降噪"), "索尼"),
                    p("jd-102", "小米入耳式耳机 白色 长续航", "京东-mock",
                            179.00, 259.00, "小米品牌旗舰店",
                            4.7, 18000, List.of("官方", "长续航", "入耳式"), "小米",
                            "xiaomi-earbud-basic"),
                    p("jd-103", "索尼头戴式降噪耳机 黑色 专业级", "京东-mock",
                            458.00, 599.00, "索尼京东自营",
                            4.8, 15000, List.of("自营", "降噪", "头戴式"), "索尼"),
                    p("jd-104", "华为运动蓝牙耳机 蓝色 防水", "京东-mock",
                            259.00, 349.00, "华为品牌专营店",
                            4.5, 9000, List.of("防水"), "华为")
            );
        }
        if (kw.contains("吹风机")) {
            return List.of(
                    p("jd-201", "飞利浦负离子护发吹风机 大功率 白色", "京东-mock",
                            199.00, 359.00, "飞利浦京东自营",
                            4.8, 15000, List.of("自营", "负离子"), "飞利浦"),
                    p("jd-202", "戴森高速吹风机 静音设计 黑色", "京东-mock",
                            349.00, 499.00, "戴森品牌旗舰店",
                            4.9, 9800, List.of("官方", "静音", "高速"), "戴森"),
                    p("jd-203", "松下便携折叠吹风机 粉色", "京东-mock",
                            149.00, 259.00, "松下京东自营",
                            4.6, 22000, List.of("自营", "便携", "折叠"), "松下"),
                    p("jd-204", "飞利浦大功率家用吹风机 白色", "京东-mock",
                            259.00, 359.00, "飞利浦品牌专营店",
                            4.5, 11000, List.of(), "飞利浦")
            );
        }
        if (kw.contains("背包")) {
            return List.of(
                    p("jd-301", "耐克双肩运动背包 黑色 大容量", "京东-mock",
                            199.00, 299.00, "耐克京东自营",
                            4.8, 12000, List.of("自营", "大容量"), "耐克"),
                    p("jd-302", "新百伦时尚背包 灰色 简约", "京东-mock",
                            259.00, 359.00, "新百伦品牌旗舰店",
                            4.7, 8000, List.of("官方", "简约"), "新百伦"),
                    p("jd-303", "阿迪达斯运动背包 黑色 防水", "京东-mock",
                            299.00, 399.00, "阿迪达斯京东自营",
                            4.8, 9500, List.of("自营", "防水"), "阿迪达斯"),
                    p("jd-304", "小米商务背包 灰色 笔记本电脑款", "京东-mock",
                            169.00, 249.00, "小米品牌专营店",
                            4.6, 15000, List.of("商务", "笔记本"), "小米")
            );
        }
        if (kw.contains("智能手表") || kw.contains("手表")) {
            return List.of(
                    p("jd-401", "苹果智能手表 银色 GPS版", "京东-mock",
                            2199.00, 2499.00, "苹果京东自营",
                            4.9, 8000, List.of("自营", "GPS"), "苹果"),
                    p("jd-402", "华为智能手表 黑色 运动款", "京东-mock",
                            999.00, 1299.00, "华为品牌旗舰店",
                            4.8, 16000, List.of("官方", "运动"), "华为"),
                    p("jd-403", "小米智能手表 黑色 长续航", "京东-mock",
                            499.00, 699.00, "小米京东自营",
                            4.7, 28000, List.of("自营", "长续航"), "小米",
                            "xiaomi-smartwatch-std"),
                    p("jd-404", "华为商务智能手表 棕色 真皮表带", "京东-mock",
                            1499.00, 1899.00, "华为品牌专营店",
                            4.6, 5200, List.of("商务"), "华为")
            );
        }
        return List.of(
                p("jd-001", "耐克品牌运动鞋 轻便透气 白色", "京东-mock",
                        299.00, 399.00, "耐克京东自营",
                        4.8, 12000, List.of("自营", "透气", "通勤"), "耐克"),
                p("jd-002", "阿迪达斯官方旗舰减震训练运动鞋 黑色", "京东-mock",
                        389.00, 499.00, "阿迪达斯官方旗舰店",
                        4.9, 8500, List.of("官方", "旗舰店", "减震", "跑步"), "阿迪达斯"),
                p("jd-003", "新百伦经典复古运动鞋 灰白色", "京东-mock",
                        459.00, 559.00, "新百伦京东自营",
                        4.7, 6200, List.of("自营", "复古"), "新百伦"),
                p("jd-004", "李宁透气网面跑步运动鞋 深蓝色", "京东-mock",
                        219.00, 299.00, "李宁品牌专营店",
                        4.4, 18000, List.of("透气", "跑步"), "李宁",
                        "lining-running-shoe")
        );
    }

    // ── PDD products ─────────────────────────────────────────────

    private List<ProductOffer> pddProducts(ProductSearchQuery query) {
        String kw = query.keyword();
        if (kw.contains("耳机")) {
            return List.of(
                    p("pdd-101", "爆款蓝牙耳机 高性价比 黑色", "拼多多-mock",
                            79.00, 199.00, "数码专营店",
                            4.3, 92000, List.of("爆款", "性价比"), null),
                    p("pdd-102", "小米无线耳机 运动款 防水 白色", "拼多多-mock",
                            129.00, 189.00, "小米耳机专营店",
                            4.2, 35000, List.of("性价比", "防水"), "小米",
                            "xiaomi-earbud-basic"),
                    p("pdd-103", "头戴式游戏耳机 黑色", "拼多多-mock",
                            239.00, 349.00, "数码专营店",
                            4.4, 28000, List.of("头戴式"), null),
                    p("pdd-104", "降噪蓝牙耳机 长续航 白色", "拼多多-mock",
                            149.00, 229.00, "品牌折扣店",
                            4.1, 56000, List.of("降噪", "长续航"), null)
            );
        }
        if (kw.contains("吹风机")) {
            return List.of(
                    p("pdd-201", "大功率吹风机 家用款 白色", "拼多多-mock",
                            59.00, 129.00, "家电专营店",
                            4.3, 68000, List.of("爆款", "性价比"), null),
                    p("pdd-202", "松下负离子护发吹风机 粉色", "拼多多-mock",
                            89.00, 159.00, "品牌折扣店",
                            4.1, 42000, List.of("性价比", "负离子"), "松下"),
                    p("pdd-203", "便携迷你吹风机 白色", "拼多多-mock",
                            79.00, 139.00, "家电专营店",
                            4.2, 35000, List.of("便携", "性价比"), null),
                    p("pdd-204", "静音高速吹风机 黑色", "拼多多-mock",
                            109.00, 199.00, "数码专营店",
                            4.4, 52000, List.of("静音", "高速", "性价比"), null)
            );
        }
        if (kw.contains("背包")) {
            return List.of(
                    p("pdd-301", "爆款双肩背包 大容量 黑色", "拼多多-mock",
                            69.00, 129.00, "潮品专营店",
                            4.2, 86000, List.of("爆款", "性价比"), null),
                    p("pdd-302", "时尚帆布背包 白色 学院风", "拼多多-mock",
                            89.00, 149.00, "时尚专营店",
                            4.3, 56000, List.of("学院风"), null),
                    p("pdd-303", "运动背包 红色 透气", "拼多多-mock",
                            99.00, 169.00, "运动专营店",
                            4.1, 42000, List.of("透气", "性价比"), null),
                    p("pdd-304", "商务双肩背包 灰色 防泼水", "拼多多-mock",
                            119.00, 199.00, "商务专营店",
                            4.4, 28000, List.of("商务", "防水"), null)
            );
        }
        if (kw.contains("智能手表") || kw.contains("手表")) {
            return List.of(
                    p("pdd-401", "智能运动手表 黑色 多功能", "拼多多-mock",
                            199.00, 399.00, "数码爆款店",
                            4.2, 62000, List.of("爆款", "性价比"), null),
                    p("pdd-402", "小米智能手表 标准版 黑色", "拼多多-mock",
                            349.00, 499.00, "小米数码专营店",
                            4.5, 48000, List.of("性价比", "长续航"), "小米",
                            "xiaomi-smartwatch-std"),
                    p("pdd-403", "时尚智能手表 粉色 女士款", "拼多多-mock",
                            259.00, 399.00, "时尚专营店",
                            4.3, 32000, List.of("时尚"), null),
                    p("pdd-404", "运动追踪手表 蓝色 防水", "拼多多-mock",
                            179.00, 299.00, "运动专营店",
                            4.4, 56000, List.of("防水", "运动"), null)
            );
        }
        return List.of(
                p("pdd-001", "爆款运动鞋 网面透气 白色", "拼多多-mock",
                        199.00, 299.00, "品牌专营店",
                        4.5, 58000, List.of("爆款", "透气"), null),
                p("pdd-002", "轻便百搭运动鞋 米色", "拼多多-mock",
                        239.00, 329.00, "运动鞋专营店",
                        4.3, 23000, List.of("性价比"), null),
                p("pdd-003", "李宁夏季透气跑步运动鞋 黑色", "拼多多-mock",
                        169.00, 249.00, "李宁品牌折扣店",
                        4.2, 78000, List.of("性价比", "跑步", "透气"), "李宁",
                        "lining-running-shoe"),
                p("pdd-004", "复古厚底运动鞋 白色", "拼多多-mock",
                        189.00, 269.00, "潮鞋专营店",
                        4.4, 45000, List.of("复古", "性价比"), null)
        );
    }

    // ── TB products ──────────────────────────────────────────────

    private List<ProductOffer> tbProducts(ProductSearchQuery query) {
        String kw = query.keyword();
        if (kw.contains("耳机")) {
            return List.of(
                    p("tb-101", "森海塞尔新款降噪耳机 时尚设计 黑色", "淘宝-mock",
                            249.00, 399.00, "森海塞尔品牌官方店",
                            4.6, 12000, List.of("官方", "降噪"), "森海塞尔"),
                    p("tb-102", "复古头戴式耳机 经典黑", "淘宝-mock",
                            199.00, 299.00, "潮品集合店",
                            4.5, 7800, List.of("复古", "头戴式"), null),
                    p("tb-103", "森海塞尔入耳式HiFi耳机 银色", "淘宝-mock",
                            359.00, 459.00, "森海塞尔品牌官方店",
                            4.7, 8500, List.of("官方", "入耳式"), "森海塞尔"),
                    p("tb-104", "华为运动防水蓝牙耳机 绿色", "淘宝-mock",
                            159.00, 249.00, "华为潮品集合店",
                            4.3, 32000, List.of("防水"), "华为")
            );
        }
        if (kw.contains("吹风机")) {
            return List.of(
                    p("tb-201", "飞利浦轻量吹风机 便携折叠 白色", "淘宝-mock",
                            129.00, 229.00, "飞利浦品牌官方店",
                            4.5, 22000, List.of("官方", "便携", "折叠"), "飞利浦"),
                    p("tb-202", "家用大功率吹风机 负离子护发", "淘宝-mock",
                            159.00, 269.00, "电器专营店",
                            4.4, 16000, List.of("负离子"), null),
                    p("tb-203", "戴森专业沙龙级吹风机 高速 黑色", "淘宝-mock",
                            299.00, 459.00, "戴森品牌官方店",
                            4.7, 12000, List.of("官方", "高速"), "戴森"),
                    p("tb-204", "迷你旅行吹风机 粉色", "淘宝-mock",
                            99.00, 169.00, "潮品集合店",
                            4.2, 28000, List.of("便携", "折叠"), null)
            );
        }
        if (kw.contains("背包")) {
            return List.of(
                    p("tb-301", "耐克官方运动背包 蓝色 时尚", "淘宝-mock",
                            229.00, 329.00, "耐克品牌官方店",
                            4.7, 16000, List.of("官方", "时尚"), "耐克"),
                    p("tb-302", "新款帆布双肩背包 灰色 文艺", "淘宝-mock",
                            159.00, 239.00, "潮品集合店",
                            4.4, 12000, List.of("文艺", "学院风"), null),
                    p("tb-303", "阿迪达斯训练背包 黑色 防泼水", "淘宝-mock",
                            259.00, 359.00, "阿迪达斯品牌官方店",
                            4.6, 8800, List.of("官方", "防水"), "阿迪达斯"),
                    p("tb-304", "复古双肩包 棕色 真皮设计", "淘宝-mock",
                            199.00, 299.00, "潮鞋集合店",
                            4.5, 9500, List.of("复古", "真皮"), null)
            );
        }
        if (kw.contains("智能手表") || kw.contains("手表")) {
            return List.of(
                    p("tb-401", "苹果智能手表 蜂窝版 银色", "淘宝-mock",
                            2899.00, 3299.00, "苹果品牌官方店",
                            4.9, 7000, List.of("官方", "蜂窝"), "苹果"),
                    p("tb-402", "华为智能手表 时尚款 玫瑰金", "淘宝-mock",
                            1099.00, 1499.00, "华为品牌官方店",
                            4.7, 14000, List.of("官方", "时尚"), "华为"),
                    p("tb-403", "小米智能手表 标准款 白色", "淘宝-mock",
                            429.00, 599.00, "小米潮品集合店",
                            4.5, 22000, List.of("性价比"), "小米",
                            "xiaomi-smartwatch-std"),
                    p("tb-404", "运动智能手表 黑色 GPS 防水", "淘宝-mock",
                            699.00, 999.00, "潮品集合店",
                            4.4, 9000, List.of("防水", "GPS"), null)
            );
        }
        return List.of(
                p("tb-001", "耐克春季新款运动鞋 百搭配色 白色", "淘宝-mock",
                        279.00, 359.00, "耐克品牌官方店",
                        4.7, 15000, List.of("官方", "通勤"), "耐克"),
                p("tb-002", "新百伦复古运动鞋 经典白色 通勤款", "淘宝-mock",
                        259.00, 339.00, "新百伦潮鞋集合店",
                        4.6, 9800, List.of("复古", "通勤"), "新百伦"),
                p("tb-003", "阿迪达斯减震训练运动鞋 黑色", "淘宝-mock",
                        329.00, 429.00, "阿迪达斯品牌官方店",
                        4.8, 22000, List.of("官方", "减震", "跑步"), "阿迪达斯"),
                p("tb-004", "厚底增高运动鞋 粉色", "淘宝-mock",
                        219.00, 289.00, "潮品集合店",
                        4.2, 31000, List.of("通勤"), null)
        );
    }

    private static ProductOffer p(String id, String title, String platform,
                                  double price, double originalPrice, String shopName,
                                  double rating, int sales, List<String> tags, String brand) {
        return new ProductOffer(id, title, platform, price, originalPrice, shopName,
                "", "", rating, sales, tags, List.of(), 0, brand);
    }

    private static ProductOffer p(String id, String title, String platform,
                                  double price, double originalPrice, String shopName,
                                  double rating, int sales, List<String> tags, String brand,
                                  String sameItemKey) {
        List<Double> priceHistory = defaultPriceHistory(price, originalPrice);
        return new ProductOffer(id, title, platform, price, originalPrice, shopName,
                "", "", rating, sales, tags, List.of(), 0, brand,
                priceHistory, List.of(), sameItemKey);
    }

    private static List<Double> defaultPriceHistory(double price, double originalPrice) {
        if (price <= 0) return List.of();
        double base = originalPrice > price ? originalPrice : price * 1.15;
        return List.of(
                Math.round(base * 100.0) / 100.0,
                Math.round(base * 0.97 * 100.0) / 100.0,
                Math.round(((base + price) / 2.0) * 100.0) / 100.0,
                Math.round(price * 1.05 * 100.0) / 100.0,
                Math.round(price * 100.0) / 100.0
        );
    }
}
