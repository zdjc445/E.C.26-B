import 'package:app_core/app_core_domain.dart';

/// Value object for search filter criteria.
class FilterCriteria {
  final double? priceMin;
  final double? priceMax;
  final String? color;
  final String? brand;
  final String? category;
  final double? minRating;
  final bool? officialOnly;
  final bool? selfOperatedOnly;
  final List<Platform>? platforms;
  final SortMode? sortBy;

  const FilterCriteria({
    this.priceMin,
    this.priceMax,
    this.color,
    this.brand,
    this.category,
    this.minRating,
    this.officialOnly,
    this.selfOperatedOnly,
    this.platforms,
    this.sortBy,
  });

  bool get hasFilters =>
      priceMin != null ||
      priceMax != null ||
      color != null ||
      brand != null ||
      category != null ||
      minRating != null ||
      officialOnly != null ||
      selfOperatedOnly != null ||
      platforms != null ||
      sortBy != null;

  bool get isPriceFilterApplied => priceMin != null || priceMax != null;

  FilterCriteria copyWith({
    double? priceMin,
    double? priceMax,
    String? color,
    String? brand,
    String? category,
    double? minRating,
    bool? officialOnly,
    bool? selfOperatedOnly,
    List<Platform>? platforms,
    SortMode? sortBy,
    bool clearColor = false,
    bool clearBrand = false,
    bool clearCategory = false,
    bool clearPrice = false,
    bool clearRating = false,
    bool clearOfficial = false,
    bool clearSelfOperated = false,
    bool clearPlatforms = false,
    bool clearSort = false,
  }) {
    return FilterCriteria(
      priceMin: clearPrice ? null : (priceMin ?? this.priceMin),
      priceMax: clearPrice ? null : (priceMax ?? this.priceMax),
      color: clearColor ? null : (color ?? this.color),
      brand: clearBrand ? null : (brand ?? this.brand),
      category: clearCategory ? null : (category ?? this.category),
      minRating: clearRating ? null : (minRating ?? this.minRating),
      officialOnly: clearOfficial ? null : (officialOnly ?? this.officialOnly),
      selfOperatedOnly: clearSelfOperated
          ? null
          : (selfOperatedOnly ?? this.selfOperatedOnly),
      platforms: clearPlatforms ? null : (platforms ?? this.platforms),
      sortBy: clearSort ? null : (sortBy ?? this.sortBy),
    );
  }

  factory FilterCriteria.fromJson(Map<String, dynamic> json) {
    return FilterCriteria(
      priceMin: _nullableNumber(json['priceMin'] ?? json['minPrice']),
      priceMax: _nullableNumber(json['priceMax'] ?? json['maxPrice']),
      color: json['color'] as String?,
      brand: json['brand'] as String?,
      category: json['category'] as String?,
      minRating: _nullableNumber(json['minRating']),
      officialOnly: json['officialOnly'] as bool?,
      selfOperatedOnly: json['selfOperatedOnly'] as bool?,
      platforms: (json['platforms'] as List<dynamic>?)
          ?.map((e) => Platform.fromApi(e.toString()))
          .toList(),
      sortBy: json['sortBy'] != null
          ? SortMode.fromApi(json['sortBy'] as String)
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{};
    if (priceMin != null) map['minPrice'] = priceMin;
    if (priceMax != null) map['maxPrice'] = priceMax;
    if (color != null) map['color'] = color;
    if (brand != null) map['brand'] = brand;
    if (category != null) map['category'] = category;
    if (minRating != null) map['minRating'] = minRating;
    if (officialOnly != null) map['officialOnly'] = officialOnly;
    if (selfOperatedOnly != null) map['selfOperatedOnly'] = selfOperatedOnly;
    if (platforms != null) {
      map['platforms'] = platforms!.map((p) => p.apiValue).toList();
    }
    if (sortBy != null) map['sortBy'] = sortBy!.apiValue;
    return map;
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is FilterCriteria &&
          priceMin == other.priceMin &&
          priceMax == other.priceMax &&
          color == other.color &&
          brand == other.brand &&
          category == other.category &&
          minRating == other.minRating &&
          officialOnly == other.officialOnly &&
          selfOperatedOnly == other.selfOperatedOnly &&
          sortBy == other.sortBy;

  @override
  int get hashCode => Object.hash(
        priceMin,
        priceMax,
        color,
        brand,
        category,
        minRating,
        officialOnly,
        selfOperatedOnly,
        sortBy,
      );
}

double? _nullableNumber(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value);
  if (value is Map) return _nullableNumber(value['amount']);
  return null;
}
