package com.ec26b.shoppingagent.product;

import java.util.*;

/**
 * In-memory hybrid vector index for product titles that combines
 * word-level and character-level tokenization for Chinese text.
 *
 * <p>Tokenization strategy (4 layers, all contributing to the same TF-IDF space):
 * <ol>
 *   <li><b>Dictionary word match</b> — match known Chinese shopping terms
 *       ("蓝牙耳机", "降噪", "运动鞋", "旗舰版"…) against the input</li>
 *   <li><b>Character bigrams</b> — sliding window of 2 characters
 *       ("运动鞋" → ["运动","动鞋"]) — good fallback for unknown compounds</li>
 *   <li><b>Unigrams</b> — individual Chinese characters for substring matching</li>
 *   <li><b>Attribute boost tokens</b> — brand and category indexed with
 *       synthetic prefix tokens ({@code __brand_Nike}, {@code __cat_耳机})
 *       to allow attribute-aware retrieval</li>
 * </ol>
 *
 * <p>The dictionary covers ~120 common shopping-domain terms (categories,
 * brands, attributes, features) and is embedded directly — no external
 * segmentation library dependency.
 */
public class ProductVectorIndex {

    private final Map<String, double[]> vectors = new LinkedHashMap<>();
    private final Map<String, Integer> termIdx = new LinkedHashMap<>();
    private final Map<String, Double> idf = new LinkedHashMap<>();
    private final List<IndexedProduct> indexed;
    private final int dim;

    public ProductVectorIndex(List<Map<String, String>> products) {
        this.indexed = products.stream()
                .map(p -> new IndexedProduct(
                        p.getOrDefault("productId", ""),
                        p.getOrDefault("title", ""),
                        p.getOrDefault("brand", ""),
                        p.getOrDefault("category", "")))
                .toList();

        // Count document frequencies
        Map<String, Integer> docFreq = new LinkedHashMap<>();
        List<List<String>> docs = new ArrayList<>();
        for (IndexedProduct p : indexed) {
            List<String> tokens = tokenizeWithAttributes(p.title, p.brand, p.category);
            docs.add(tokens);
            for (String t : new LinkedHashSet<>(tokens)) {
                docFreq.merge(t, 1, Integer::sum);
            }
        }

        // Build term index and idf
        int idx = 0;
        for (String term : docFreq.keySet()) {
            termIdx.put(term, idx++);
        }
        this.dim = termIdx.size();
        int N = indexed.size();
        for (var entry : docFreq.entrySet()) {
            idf.put(entry.getKey(), Math.log((double) N / (1 + entry.getValue())));
        }

        // Build unit vectors
        for (int i = 0; i < indexed.size(); i++) {
            double[] vec = tfidfVector(docs.get(i));
            double norm = norm(vec);
            if (norm > 0) {
                for (int j = 0; j < vec.length; j++) vec[j] /= norm;
            }
            vectors.put(indexed.get(i).productId, vec);
        }
    }

    /**
     * Search top-K products by cosine similarity to query.
     *
     * <p>Query tokens include dictionary words, bigrams, and unigrams.
     * Brand/category attribute tokens are also matched if the query
     * contains a known brand or category keyword.
     */
    public List<ScoredProduct> search(String query, int topK) {
        if (query == null || query.isBlank() || dim == 0) {
            return indexed.stream().limit(topK)
                    .map(p -> new ScoredProduct(p.productId, 1.0)).toList();
        }

        // Tokenize query with attribute matching
        List<String> qTokens = tokenizeWithAttributeDetection(query);

        double[] queryVec = tfidfVector(qTokens);
        normalize(queryVec);

        List<ScoredProduct> results = new ArrayList<>();
        for (IndexedProduct p : indexed) {
            double[] pVec = vectors.get(p.productId);
            if (pVec == null) continue;
            double sim = dot(queryVec, pVec);
            if (sim > 0) results.add(new ScoredProduct(p.productId, sim));
        }

        results.sort((a, b) -> Double.compare(b.score, a.score));
        return results.stream().limit(topK).toList();
    }

    // ── Tokenization with attribute enhancement ──────────────────

    /**
     * Tokenize a title with brand and category attribute boost tokens.
     * Used when building the index.
     */
    static List<String> tokenizeWithAttributes(String title, String brand, String category) {
        List<String> tokens = new ArrayList<>(tokenize(title));
        // Attribute boost tokens — prefixed to avoid collision with normal text
        if (brand != null && !brand.isBlank()) {
            tokens.add("__brand_" + brand.toLowerCase().replaceAll("\\s+", ""));
        }
        if (category != null && !category.isBlank()) {
            tokens.add("__cat_" + category);
        }
        return tokens;
    }

    /**
     * Tokenize a user query and add attribute boost tokens when the query
     * contains known brands or category keywords.
     */
    static List<String> tokenizeWithAttributeDetection(String query) {
        List<String> tokens = new ArrayList<>(tokenize(query));
        String lower = query.toLowerCase();

        // Detect known brands in the query
        for (String brand : KNOWN_BRANDS) {
            if (lower.contains(brand.toLowerCase())) {
                tokens.add("__brand_" + brand.toLowerCase().replaceAll("\\s+", ""));
            }
        }
        // Detect known category keywords
        for (String cat : KNOWN_CATEGORIES) {
            if (lower.contains(cat)) {
                tokens.add("__cat_" + cat);
            }
        }
        return tokens;
    }

    /**
     * Multi-layer tokenization for Chinese + English text.
     *
     * <p>Layer 1: Dictionary word matching (greedy left-to-right)
     * <p>Layer 2: Character bigrams (sliding window, len=2)
     * <p>Layer 3: Character unigrams
     * <p>Layer 4: English word tokens (whitespace-split, len ≥ 2)
     */
    static List<String> tokenize(String text) {
        if (text == null || text.isBlank()) return List.of();
        List<String> tokens = new ArrayList<>();

        // Pre-clean: normalize spaces but keep CJK intact
        String cleaned = text.replaceAll("[^\\u4e00-\\u9fa5a-zA-Z0-9\\s]", " ");

        // --- Layer 1: Dictionary word matching (greedy) ---
        String remaining = cleaned;
        int pos = 0;
        while (pos < remaining.length()) {
            boolean matched = false;
            // Try longest match first (max word length in dict ≈ 6 chars)
            for (int len = Math.min(6, remaining.length() - pos); len >= 2; len--) {
                String candidate = remaining.substring(pos, pos + len);
                if (KNOWN_WORDS.contains(candidate)) {
                    tokens.add(candidate);
                    pos += len;
                    matched = true;
                    break;
                }
            }
            if (!matched) {
                pos++;
            }
        }

        // --- Layer 2: Character bigrams (CJK + alphanumeric) ---
        String compact = cleaned.replaceAll("\\s+", "");
        for (int i = 0; i < compact.length() - 1; i++) {
            tokens.add(compact.substring(i, i + 2));
        }

        // --- Layer 3: Character unigrams (CJK only, for substring matching) ---
        for (int i = 0; i < compact.length(); i++) {
            char c = compact.charAt(i);
            if (Character.UnicodeBlock.of(c) == Character.UnicodeBlock.CJK_UNIFIED_IDEOGRAPHS) {
                tokens.add(String.valueOf(c));
            }
        }

        // --- Layer 4: English word tokens ---
        for (String word : text.toLowerCase().split("[\\s,，、]+")) {
            String w = word.replaceAll("[^a-z0-9]", "");
            if (w.length() >= 2) tokens.add(w);
        }

        return tokens;
    }

    // ── Vector math ──────────────────────────────────────────────

    private double[] tfidfVector(List<String> tokens) {
        double[] vec = new double[dim];
        Map<String, Long> tf = new LinkedHashMap<>();
        for (String t : tokens) {
            tf.merge(t, 1L, Long::sum);
        }
        // Sub-linear TF scaling: log(1 + tf)
        for (var entry : tf.entrySet()) {
            Integer i = termIdx.get(entry.getKey());
            if (i != null) {
                vec[i] = Math.log(1 + entry.getValue()) * idf.getOrDefault(entry.getKey(), 0.0);
            }
        }
        return vec;
    }

    private void normalize(double[] v) {
        double n = norm(v);
        if (n > 0) for (int i = 0; i < v.length; i++) v[i] /= n;
    }

    private static double norm(double[] v) {
        return Math.sqrt(Arrays.stream(v).map(x -> x * x).sum());
    }

    private static double dot(double[] a, double[] b) {
        double sum = 0;
        int n = Math.min(a.length, b.length);
        for (int i = 0; i < n; i++) sum += a[i] * b[i];
        return sum; // unit vectors → dot = cosine similarity
    }

    // ── DTOs ─────────────────────────────────────────────────────

    private record IndexedProduct(String productId, String title, String brand, String category) {}

    public record ScoredProduct(String productId, double score) {}

    // ── Embedded Chinese shopping-domain dictionary (~120 words) ──

    private static final Set<String> KNOWN_WORDS = Set.of(
            // Categories & subcategories
            "运动鞋", "跑步鞋", "篮球鞋", "休闲鞋", "板鞋", "帆布鞋",
            "足球鞋", "训练鞋", "网面鞋", "厚底鞋", "复古鞋",
            "耳机", "蓝牙耳机", "无线耳机", "头戴式耳机", "入耳式",
            "真无线", "降噪耳机", "游戏耳机", "运动耳机", "监听耳机",
            "吹风机", "电吹风", "负离子", "护发", "造型",
            "背包", "双肩包", "单肩包", "斜挎包", "旅行包",
            "电脑包", "登山包", "商务包", "运动背包",
            "智能手表", "运动手表", "智能手环", "电子表",

            // Brands (lowercase match handled via case-insensitive comparison)
            "耐克", "阿迪达斯", "亚瑟士", "彪马", "索尼",
            "戴森", "飞利浦", "松下", "小米", "华为",
            "新秀丽", "瑞士军刀", "北极狐",
            "苹果", "三星", "佳明", "Fitbit",

            // Features / attributes
            "降噪", "无线", "蓝牙", "便携", "折叠", "触屏",
            "防水", "透气", "缓震", "回弹", "轻量",
            "长续航", "快充", "大容量", "高功率", "恒温",
            "官方", "旗舰", "自营", "正品", "联名", "限量",
            "高性价比", "便宜", "百搭", "新款", "经典款",
            "静音", "环绕声", "重低音", "高音质",
            "心率", "血氧", "GPS", "NFC", "支付",

            // Shopping modifiers
            "男款", "女款", "中性", "大码", "小码",
            "黑色", "白色", "红色", "蓝色", "绿色", "粉色",
            "紫色", "灰色", "银色", "金色", "米色",
            "高级", "专业", "学生", "入门", "进阶"
    );

    /** Known brand names for attribute-token detection in user queries. */
    private static final Set<String> KNOWN_BRANDS = Set.of(
            "Nike", "Adidas", "Asics", "Puma", "Sony",
            "戴森", "飞利浦", "松下", "小米", "华为",
            "新秀丽", "瑞士军刀", "北极狐",
            "Apple", "Samsung", "Garmin", "Fitbit",
            "耐克", "阿迪达斯", "亚瑟士", "彪马",
            "苹果", "三星", "佳明"
    );

    /** Known category names for attribute-token detection in user queries. */
    private static final Set<String> KNOWN_CATEGORIES = Set.of(
            "运动鞋", "耳机", "吹风机", "背包", "智能手表"
    );
}
