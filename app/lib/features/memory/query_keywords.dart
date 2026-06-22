/// Lightweight query-to-structured-field extractor.
///
/// Parses a free-text search query and extracts structured signals that the
/// profile engine can use: category, brand, price range.
///
/// This mirrors the backend [CategoryResolver] taxonomy but runs locally so
/// search events gain useful fields for [ProfileEngine.infer].
class QueryKeywordExtractor {
  const QueryKeywordExtractor();

  /// Result of extracting structured signals from a search query.
  QueryKeywords extract(String query) {
    if (query.isEmpty) return const QueryKeywords();
    final q = _normalize(query);
    return QueryKeywords(
      category: _findCategory(q),
      brand: _findBrand(q),
      priceMax: _findPriceMax(q),
      priceMin: _findPriceMin(q),
      categoryScore: _categoryScore(q),
    );
  }

  // ── Taxonomy (mirrors backend/src/main/resources/data/category-taxonomy.json) ──────

  static const _taxonomy = <({String name, List<String> aliases})>[
    (name: '运动鞋', aliases: [
      '运动鞋', '跑鞋', '跑步鞋', '篮球鞋', '训练鞋', '板鞋', '休闲运动鞋',
    ]),
    (name: '耳机', aliases: [
      '耳机', '蓝牙耳机', '头戴式蓝牙耳机', '头戴式耳机', '真无线蓝牙耳机',
      '真无线耳机', '入耳式耳机', '降噪耳机', 'tws耳机',
    ]),
    (name: '吹风机', aliases: [
      '吹风机', '电吹风', '高速吹风机', '负离子吹风机', '大功率吹风机',
    ]),
    (name: '背包', aliases: [
      '背包', '书包', '双肩包', '电脑包', '通勤背包', '商务背包',
    ]),
    (name: '智能手表', aliases: [
      '智能手表', '手表', '运动手表', '电话手表', '健康手表',
    ]),
  ];

  // ── Common brands ────────────────────────────────────────────

  static const _brands = <String>[
    // Headphones / audio
    'sony', 'bose', 'apple', 'sennheiser', 'jbl', 'beats', 'xiaomi',
    'huawei', 'oppo', 'vivo', 'samsung', 'anker', 'soundcore',
    '漫步者', '小米', '华为', 'oppo', 'vivo', '三星',
    // Shoes
    'nike', 'adidas', 'puma', 'newbalance', 'asics', 'converse',
    'lining', 'anta', 'xtep', '361', 'peak',
    '耐克', '阿迪达斯', '新百伦', '亚瑟士', '匡威', '李宁', '安踏',
    '特步', '匹克', '乔丹',
    // Hair dryers
    'dyson', 'panasonic', 'philips', 'flyco', 'tescom',
    '戴森', '松下', '飞利浦', '飞科',
    // Backpacks
    'jansport', 'herschel', 'tumi', 'osprey', 'victorinox',
    // Smart watches
    'garmin', 'fitbit', 'amazfit', 'suunto',
    '佳明', '华米',
  ];

  // ── Category ─────────────────────────────────────────────────

  String? _findCategory(String q) {
    for (final entry in _taxonomy) {
      for (final alias in entry.aliases) {
        final na = _normalize(alias);
        if (na.isNotEmpty && q.contains(na)) {
          return entry.name;
        }
      }
    }
    return null;
  }

  /// Weighted heuristic: longer alias match = stronger signal.
  double _categoryScore(String q) {
    double best = 0;
    for (final entry in _taxonomy) {
      for (final alias in entry.aliases) {
        final na = _normalize(alias);
        if (na.length >= 2 && q.contains(na)) {
          final s = na.length / q.length;
          if (s > best) best = s;
        }
      }
    }
    return best;
  }

  // ── Brand ────────────────────────────────────────────────────

  String? _findBrand(String q) {
    String? best;
    int bestLen = 0;
    for (final b in _brands) {
      if (q.contains(b) && b.length > bestLen) {
        best = b;
        bestLen = b.length;
      }
    }
    return best; // already normalized
  }

  // ── Price ────────────────────────────────────────────────────

  /// Extracts a max-budget hint: "500以内", "不超过1000", "预算300" etc.
  double? _findPriceMax(String q) {
    final patterns = [
      RegExp(r'(\d+)\s*以内'),
      RegExp(r'不超过\s*(\d+)'),
      RegExp(r'预算\s*(\d+)'),
      RegExp(r'(\d+)\s*以下'),
      RegExp(r'低于\s*(\d+)'),
    ];
    double? result;
    for (final re in patterns) {
      final m = re.firstMatch(q);
      if (m != null) {
        final v = double.tryParse(m.group(1)!);
        if (v != null && (result == null || v < result)) result = v;
      }
    }
    return result;
  }

  /// Extracts a min-price hint: "100以上", "不低于200" etc.
  double? _findPriceMin(String q) {
    final patterns = [
      RegExp(r'(\d+)\s*以上'),
      RegExp(r'不低于\s*(\d+)'),
      RegExp(r'至少\s*(\d+)'),
    ];
    double? result;
    for (final re in patterns) {
      final m = re.firstMatch(q);
      if (m != null) {
        final v = double.tryParse(m.group(1)!);
        if (v != null && (result == null || v > result)) result = v;
      }
    }
    return result;
  }

  // ── Normalize ────────────────────────────────────────────────

  static String _normalize(String s) {
    // Lowercase + strip non-alphanumeric for matching
    return s.toLowerCase().replaceAll(RegExp(r'[^一-鿿\w]'), '');
  }
}

/// Structured signals extracted from a search query.
class QueryKeywords {
  final String? category;
  final String? brand;
  final double? priceMax;
  final double? priceMin;
  final double categoryScore;

  const QueryKeywords({
    this.category,
    this.brand,
    this.priceMax,
    this.priceMin,
    this.categoryScore = 0,
  });

  bool get hasSignal => category != null || brand != null || priceMax != null;
}
