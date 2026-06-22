package com.ec26b.shoppingagent.product;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.io.ClassPathResource;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Lightweight taxonomy retrieval for category normalization.
 *
 * <p>The current delivery uses local taxonomy data. A production deployment can
 * keep this API and replace the internals with search / vector retrieval that
 * returns standard category ids and names.
 */
public class CategoryResolver {

    private static final CategoryResolver DEFAULT = loadDefault();

    private final List<CategoryEntry> categories;

    public CategoryResolver(List<CategoryEntry> categories) {
        this.categories = categories == null ? List.of() : List.copyOf(categories);
    }

    public static CategoryResolver defaultResolver() {
        return DEFAULT;
    }

    public String resolveName(String text) {
        String normalizedText = normalize(text);
        if (normalizedText.isBlank()) {
            return null;
        }

        for (CategoryEntry category : categories) {
            if (normalizedText.equals(normalize(category.name()))) {
                return category.name();
            }
        }
        for (CategoryEntry category : categories) {
            for (String alias : category.aliases()) {
                if (normalizedText.equals(normalize(alias))) {
                    return category.name();
                }
            }
        }
        for (CategoryEntry category : categories) {
            for (String alias : category.aliases()) {
                String normalizedAlias = normalize(alias);
                if (!normalizedAlias.isBlank() && normalizedText.contains(normalizedAlias)) {
                    return category.name();
                }
            }
        }
        for (CategoryEntry category : categories) {
            for (String alias : category.aliases()) {
                String normalizedAlias = normalize(alias);
                if (normalizedText.length() >= 2 && normalizedAlias.contains(normalizedText)) {
                    return category.name();
                }
            }
        }

        String bestName = null;
        double bestScore = 0;
        for (CategoryEntry category : categories) {
            for (String alias : category.aliases()) {
                double score = overlapScore(normalizedText, normalize(alias));
                if (score > bestScore) {
                    bestScore = score;
                    bestName = category.name();
                }
            }
        }
        return bestScore >= 0.6 ? bestName : null;
    }

    public boolean isSupportedCategory(String category) {
        String normalized = normalize(category);
        if (normalized.isBlank()) {
            return false;
        }
        for (CategoryEntry entry : categories) {
            if (normalized.equals(normalize(entry.name()))) {
                return true;
            }
        }
        return false;
    }

    public List<String> supportedCategoryNames() {
        return categories.stream().map(CategoryEntry::name).toList();
    }

    public List<String> attributesFor(String categoryName) {
        String resolved = resolveName(categoryName);
        if (resolved == null) {
            return List.of();
        }
        for (CategoryEntry entry : categories) {
            if (entry.name().equals(resolved)) {
                return entry.attributes();
            }
        }
        return List.of();
    }

    private static CategoryResolver loadDefault() {
        ObjectMapper objectMapper = new ObjectMapper();
        try (InputStream in = new ClassPathResource("data/category-taxonomy.json").getInputStream()) {
            List<CategoryEntry> entries = objectMapper.readValue(in, new TypeReference<>() {});
            if (!entries.isEmpty()) {
                return new CategoryResolver(entries);
            }
        } catch (IOException ignored) {
            // Keep local fallback so tests and dev runs remain available if resources are missing.
        }
        return new CategoryResolver(fallbackTaxonomy());
    }

    private static List<CategoryEntry> fallbackTaxonomy() {
        return List.of(
                new CategoryEntry("cat-shoes", "运动鞋",
                        List.of("运动鞋", "跑鞋", "跑步鞋", "篮球鞋", "训练鞋", "板鞋", "休闲运动鞋"),
                        List.of("品牌", "颜色", "尺码", "鞋面材质", "缓震", "适用场景")),
                new CategoryEntry("cat-headphones", "耳机",
                        List.of("耳机", "蓝牙耳机", "头戴式蓝牙耳机", "头戴式耳机", "真无线蓝牙耳机",
                                "真无线耳机", "入耳式耳机", "降噪耳机", "TWS耳机"),
                        List.of("品牌", "颜色", "佩戴方式", "降噪", "连接方式", "续航")),
                new CategoryEntry("cat-hair-dryer", "吹风机",
                        List.of("吹风机", "电吹风", "高速吹风机", "负离子吹风机", "大功率吹风机"),
                        List.of("品牌", "颜色", "功率", "风速", "负离子", "重量")),
                new CategoryEntry("cat-backpack", "背包",
                        List.of("背包", "书包", "双肩包", "电脑包", "通勤背包", "商务背包"),
                        List.of("品牌", "颜色", "容量", "材质", "风格", "防水")),
                new CategoryEntry("cat-smartwatch", "智能手表",
                        List.of("智能手表", "手表", "运动手表", "电话手表", "健康手表"),
                        List.of("品牌", "颜色", "续航", "运动模式", "防水", "系统兼容"))
        );
    }

    private static String normalize(String value) {
        if (value == null) {
            return "";
        }
        String lower = value.toLowerCase(Locale.ROOT);
        StringBuilder result = new StringBuilder();
        lower.codePoints().forEach(cp -> {
            if (Character.isLetterOrDigit(cp)) {
                result.appendCodePoint(cp);
            }
        });
        return result.toString();
    }

    private static double overlapScore(String left, String right) {
        if (left.length() < 2 || right.length() < 2) {
            return 0;
        }
        Set<Integer> leftChars = codePointSet(left);
        Set<Integer> rightChars = codePointSet(right);
        if (leftChars.isEmpty() || rightChars.isEmpty()) {
            return 0;
        }
        Set<Integer> intersection = new LinkedHashSet<>(leftChars);
        intersection.retainAll(rightChars);
        if (intersection.size() < 2) {
            return 0;
        }
        return (double) intersection.size() / Math.min(leftChars.size(), rightChars.size());
    }

    private static Set<Integer> codePointSet(String value) {
        Set<Integer> result = new LinkedHashSet<>();
        value.codePoints().forEach(result::add);
        return result;
    }

    public record CategoryEntry(String categoryId, String name,
                                List<String> aliases, List<String> attributes) {
        public CategoryEntry {
            aliases = aliases == null ? List.of() : List.copyOf(new ArrayList<>(aliases));
            attributes = attributes == null ? List.of() : List.copyOf(new ArrayList<>(attributes));
        }
    }
}
