import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'memory_store.dart';

// ── Providers ──────────────────────────────────────────────────────────────

final userProfileProvider = StateNotifierProvider<UserProfileNotifier, UserProfile>((ref) {
  return UserProfileNotifier(ref.watch(memoryStoreProvider));
});

// ── Model ──────────────────────────────────────────────────────────────────

class UserProfile {
  // ── Explicit (user-set) preferences ──
  final List<String> preferredPlatforms;
  final List<String> preferredCategories;
  final Map<String, double> categoryMaxBudget;
  final List<String> decisionFactors;   // low_price, official_store, after_sale, fast_delivery, high_rating, brand_match
  final List<String> dislikes;          // no_brand, loud_color, non_official, high_price

  // ── Behavior-inferred preferences ──
  final List<String> inferredCategories;
  final double? inferredPriceMin;
  final double? inferredPriceMax;
  final List<String> inferredPlatforms;
  final List<String> inferredBrands;
  final List<String> recentInterests;   // last 7 days

  // ── Control flags ──
  final bool personalizationEnabled;

  const UserProfile({
    this.preferredPlatforms = const [],
    this.preferredCategories = const [],
    this.categoryMaxBudget = const {},
    this.decisionFactors = const [],
    this.dislikes = const [],
    this.inferredCategories = const [],
    this.inferredPriceMin,
    this.inferredPriceMax,
    this.inferredPlatforms = const [],
    this.inferredBrands = const [],
    this.recentInterests = const [],
    this.personalizationEnabled = true,
  });

  bool get isEmpty =>
      preferredPlatforms.isEmpty &&
      preferredCategories.isEmpty &&
      decisionFactors.isEmpty &&
      dislikes.isEmpty &&
      inferredCategories.isEmpty;

  UserProfile copyWith({
    List<String>? preferredPlatforms,
    List<String>? preferredCategories,
    Map<String, double>? categoryMaxBudget,
    List<String>? decisionFactors,
    List<String>? dislikes,
    List<String>? inferredCategories,
    double? inferredPriceMin,
    double? inferredPriceMax,
    List<String>? inferredPlatforms,
    List<String>? inferredBrands,
    List<String>? recentInterests,
    bool? personalizationEnabled,
  }) {
    return UserProfile(
      preferredPlatforms: preferredPlatforms ?? this.preferredPlatforms,
      preferredCategories: preferredCategories ?? this.preferredCategories,
      categoryMaxBudget: categoryMaxBudget ?? this.categoryMaxBudget,
      decisionFactors: decisionFactors ?? this.decisionFactors,
      dislikes: dislikes ?? this.dislikes,
      inferredCategories: inferredCategories ?? this.inferredCategories,
      inferredPriceMin: inferredPriceMin ?? this.inferredPriceMin,
      inferredPriceMax: inferredPriceMax ?? this.inferredPriceMax,
      inferredPlatforms: inferredPlatforms ?? this.inferredPlatforms,
      inferredBrands: inferredBrands ?? this.inferredBrands,
      recentInterests: recentInterests ?? this.recentInterests,
      personalizationEnabled: personalizationEnabled ?? this.personalizationEnabled,
    );
  }

  // ── Serialization ──────────────────────────────────────────

  Map<String, dynamic> toJson() => {
    'preferredPlatforms': preferredPlatforms,
    'preferredCategories': preferredCategories,
    'categoryMaxBudget': Map<String, dynamic>.from(categoryMaxBudget),
    'decisionFactors': decisionFactors,
    'dislikes': dislikes,
    'inferredCategories': inferredCategories,
    'inferredPriceMin': inferredPriceMin,
    'inferredPriceMax': inferredPriceMax,
    'inferredPlatforms': inferredPlatforms,
    'inferredBrands': inferredBrands,
    'recentInterests': recentInterests,
    'personalizationEnabled': personalizationEnabled,
  };

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      preferredPlatforms: _stringList(json['preferredPlatforms']),
      preferredCategories: _stringList(json['preferredCategories']),
      categoryMaxBudget: _doubleMap(json['categoryMaxBudget']),
      decisionFactors: _stringList(json['decisionFactors']),
      dislikes: _stringList(json['dislikes']),
      inferredCategories: _stringList(json['inferredCategories']),
      inferredPriceMin: (json['inferredPriceMin'] as num?)?.toDouble(),
      inferredPriceMax: (json['inferredPriceMax'] as num?)?.toDouble(),
      inferredPlatforms: _stringList(json['inferredPlatforms']),
      inferredBrands: _stringList(json['inferredBrands']),
      recentInterests: _stringList(json['recentInterests']),
      personalizationEnabled: json['personalizationEnabled'] as bool? ?? true,
    );
  }

  static List<String> _stringList(dynamic v) {
    if (v is List) return v.map((e) => e.toString()).toList();
    return [];
  }

  static Map<String, double> _doubleMap(dynamic v) {
    if (v is Map) {
      return Map<String, double>.from(
        v.map((k, val) => MapEntry(k.toString(), (val as num).toDouble())));
    }
    return {};
  }
}

// ── Notifier ───────────────────────────────────────────────────────────────

class UserProfileNotifier extends StateNotifier<UserProfile> {
  final MemoryStore _store;

  UserProfileNotifier(this._store) : super(const UserProfile()) {
    _load();
  }

  Future<void> _load() async {
    final data = await _store.loadProfile();
    if (data != null) {
      state = UserProfile.fromJson(data);
    }
    final enabled = await _store.isPersonalizationEnabled();
    if (state.personalizationEnabled != enabled) {
      state = state.copyWith(personalizationEnabled: enabled);
    }
  }

  Future<void> _save() async {
    await _store.saveProfile(state.toJson());
    await _store.setPersonalizationEnabled(state.personalizationEnabled);
  }

  // ── Explicit updates ───────────────────────────────────────

  Future<void> setPreferredPlatforms(List<String> v) async {
    state = state.copyWith(preferredPlatforms: v);
    await _save();
  }

  Future<void> setPreferredCategories(List<String> v) async {
    state = state.copyWith(preferredCategories: v);
    await _save();
  }

  Future<void> setCategoryBudget(String category, double maxPrice) async {
    final budgets = Map<String, double>.from(state.categoryMaxBudget);
    budgets[category] = maxPrice;
    state = state.copyWith(categoryMaxBudget: budgets);
    await _save();
  }

  Future<void> setDecisionFactors(List<String> v) async {
    state = state.copyWith(decisionFactors: v);
    await _save();
  }

  Future<void> setDislikes(List<String> v) async {
    state = state.copyWith(dislikes: v);
    await _save();
  }

  // ── Inferred management ────────────────────────────────────

  Future<void> removeInferredBrand(String brand) async {
    final brands = [...state.inferredBrands];
    brands.remove(brand);
    state = state.copyWith(inferredBrands: brands);
    await _save();
  }

  Future<void> removeInferredPlatform(String platform) async {
    final platforms = [...state.inferredPlatforms];
    platforms.remove(platform);
    state = state.copyWith(inferredPlatforms: platforms);
    await _save();
  }

  Future<void> removeInferredCategory(String category) async {
    final cats = [...state.inferredCategories];
    cats.remove(category);
    state = state.copyWith(inferredCategories: cats);
    await _save();
  }

  // ── Control ────────────────────────────────────────────────

  Future<void> setPersonalizationEnabled(bool v) async {
    state = state.copyWith(personalizationEnabled: v);
    await _save();
  }

  /// Run ProfileEngine.infer() against stored events and merge results.
  /// Call this after significant behavior events (search, click, view, etc.)
  Future<void> refreshInferred() async {
    if (!state.personalizationEnabled) return;
    final events = await _store.loadEvents();
    final updated = ProfileEngine.infer(events, state);
    state = updated;
    await _store.saveProfile(updated.toJson());
  }

  Future<void> clearAll(MemoryStore store) async {
    state = const UserProfile();
    await store.clearAll();
  }
}

// ── Profile Engine (behavior → inferred profile) ──────────────────────────

/// Aggregates behavior events into an inferred user profile.
/// Signal weights: search=1, productView=2, productClick=3, favorite=5,
/// platformJump=5, priceAlertCreate=4.
/// Recent = last 7 days; time decay applied within that window.
class ProfileEngine {
  /// Compute inferred profile from behavior events.
  /// Explicit preferences take priority — this only fills in gaps.
  static UserProfile infer(
    List<Map<String, dynamic>> events,
    UserProfile explicit,
  ) {
    if (events.isEmpty) return explicit;

    final now = DateTime.now();

    // Collect weighted signals from recent events
    final catWeights = <String, double>{};
    final platformWeights = <String, double>{};
    final brandWeights = <String, double>{};
    final prices = <double>[];

    for (final e in events) {
      final ts = DateTime.tryParse(e['timestamp'] as String? ?? '');
      if (ts == null) continue;
      final age = now.difference(ts).inHours;
      if (age > 24 * 7) continue; // skip older than 7 days
      final decay = _decay(age);   // time decay factor

      final weight = _signalWeight(e['type'] as String? ?? '') * decay;
      if (weight <= 0) continue;

      final cat = e['category'] as String?;
      if (cat != null && cat.isNotEmpty) {
        catWeights[cat] = (catWeights[cat] ?? 0) + weight;
      }
      final plat = e['platform'] as String?;
      if (plat != null && plat.isNotEmpty) {
        platformWeights[plat] = (platformWeights[plat] ?? 0) + weight;
      }
      final brand = e['brand'] as String?;
      if (brand != null && brand.isNotEmpty) {
        brandWeights[brand] = (brandWeights[brand] ?? 0) + weight;
      }
      final price = (e['price'] as num?)?.toDouble();
      if (price != null && price > 0) prices.add(price);
    }

    // Derive inferred fields (only if explicit doesn't already set them)
    return explicit.copyWith(
      inferredCategories: _topN(catWeights, 3),
      inferredPlatforms: _topN(platformWeights, 2),
      inferredBrands: _topN(brandWeights, 3),
      inferredPriceMin: prices.isNotEmpty ? _percentile(prices, 0.25) : explicit.inferredPriceMin,
      inferredPriceMax: prices.isNotEmpty ? _percentile(prices, 0.75) : explicit.inferredPriceMax,
      recentInterests: _topN(catWeights, 2),
    );
  }

  static double _signalWeight(String type) => switch (type) {
    'search' => 1.0,
    'productView' => 2.0,
    'productClick' => 3.0,
    'priceAlertCreate' => 4.0,
    'favorite' => 5.0,
    'platformJump' => 5.0,
    'unfavorite' => -2.0,
    _ => 0.0,
  };

  /// Exponential time decay: weight halves every ~48 hours.
  static double _decay(int hours) {
    if (hours <= 0) return 1.0;
    return 1.0 / (1.0 + hours / 48.0);
  }

  static List<String> _topN(Map<String, double> weighted, int n) {
    final sorted = weighted.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return sorted.take(n).where((e) => e.value >= 1.0).map((e) => e.key).toList();
  }

  static double _percentile(List<double> values, double p) {
    final sorted = [...values]..sort();
    final idx = (p * (sorted.length - 1)).round();
    return sorted[idx.clamp(0, sorted.length - 1)];
  }
}
