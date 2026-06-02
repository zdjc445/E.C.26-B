import 'package:app_core/app_core_domain.dart';

/// Domain entity representing a platform-level price statistic within a comparison.
class PlatformStat {
  final String platform;
  final int productCount;
  final Money lowestPrice;
  final Money highestPrice;
  final Money averagePrice;
  final String? deliveryEstimate;
  final int inStockCount;

  const PlatformStat({
    required this.platform,
    required this.productCount,
    required this.lowestPrice,
    required this.highestPrice,
    required this.averagePrice,
    this.deliveryEstimate,
    this.inStockCount = 0,
  });

  factory PlatformStat.fromJson(Map<String, dynamic> json) {
    final lowest = json['lowestPrice'];
    final highest = json['highestPrice'] ?? json['averagePrice'] ?? lowest;
    final average = json['averagePrice'] ?? lowest;
    return PlatformStat(
      platform: json['platform'] as String? ?? '',
      productCount: _intValue(json['productCount'] ?? json['resultCount']) ?? 0,
      lowestPrice: Money.fromJson(_moneyMap(lowest)),
      highestPrice: Money.fromJson(_moneyMap(highest)),
      averagePrice: Money.fromJson(_moneyMap(average)),
      deliveryEstimate: json['deliveryEstimate'] as String?,
      inStockCount: _intValue(json['inStockCount']) ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
        'platform': platform,
        'productCount': productCount,
        'lowestPrice': lowestPrice.toJson(),
        'highestPrice': highestPrice.toJson(),
        'averagePrice': averagePrice.toJson(),
        'deliveryEstimate': deliveryEstimate,
        'inStockCount': inStockCount,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PlatformStat && platform == other.platform;
  @override
  int get hashCode => platform.hashCode;
}

/// Domain entity representing a single product row in a comparison.
class ComparisonItem {
  final String platformProductId;
  final String platform;
  final String title;
  final Money price;
  final String? imageUrl;
  final double? rating;
  final int? reviewCount;
  final String? store;
  final String? url;
  final bool inStock;
  final String? deliveryInfo;
  final List<String> features;

  const ComparisonItem({
    required this.platformProductId,
    required this.platform,
    required this.title,
    required this.price,
    this.imageUrl,
    this.rating,
    this.reviewCount,
    this.store,
    this.url,
    this.inStock = true,
    this.deliveryInfo,
    this.features = const [],
  });

  factory ComparisonItem.fromJson(Map<String, dynamic> json) {
    return ComparisonItem(
      platformProductId: json['platformProductId']?.toString() ?? '',
      platform: json['platform'] as String? ?? '',
      title: json['title'] as String? ?? '',
      price: Money.fromJson(_moneyMap(json['price'])),
      imageUrl: json['imageUrl'] as String?,
      rating: (json['rating'] as num?)?.toDouble(),
      reviewCount: _intValue(json['reviewCount']),
      store: json['store'] as String? ?? json['shopName'] as String?,
      url: json['url'] as String? ?? json['productUrl'] as String?,
      inStock: json['inStock'] as bool? ?? true,
      deliveryInfo: json['deliveryInfo'] as String?,
      features: ((json['features'] ?? json['tags'] ?? json['matchReasons'])
                  as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
    );
  }

  Map<String, dynamic> toJson() => {
        'platformProductId': platformProductId,
        'platform': platform,
        'title': title,
        'price': price.toJson(),
        'imageUrl': imageUrl,
        'rating': rating,
        'reviewCount': reviewCount,
        'store': store,
        'url': url,
        'inStock': inStock,
        'deliveryInfo': deliveryInfo,
        'features': features,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ComparisonItem && platformProductId == other.platformProductId;
  @override
  int get hashCode => platformProductId.hashCode;
}

/// Domain entity for a full product comparison result.
class ComparisonEntity {
  final String comparisonId;
  final String searchTaskId;
  final String? lowestPlatformProductId;
  final Money lowestPrice;
  final List<PlatformStat> platformStats;
  final List<ComparisonItem> items;
  final DateTime createdAt;

  const ComparisonEntity({
    required this.comparisonId,
    required this.searchTaskId,
    this.lowestPlatformProductId,
    required this.lowestPrice,
    this.platformStats = const [],
    this.items = const [],
    required this.createdAt,
  });

  factory ComparisonEntity.fromJson(Map<String, dynamic> json) {
    return ComparisonEntity(
      comparisonId: json['comparisonId']?.toString() ?? '',
      searchTaskId: json['searchTaskId']?.toString() ?? '',
      lowestPlatformProductId: json['lowestPlatformProductId']?.toString(),
      lowestPrice: Money.fromJson(_moneyMap(json['lowestPrice'])),
      platformStats: (json['platformStats'] as List<dynamic>?)
              ?.map((e) => PlatformStat.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      items: (json['items'] as List<dynamic>?)
              ?.map((e) => ComparisonItem.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      createdAt: json['createdAt'] != null
          ? DateTime.parse(json['createdAt'] as String)
          : DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'comparisonId': comparisonId,
        'searchTaskId': searchTaskId,
        'lowestPlatformProductId': lowestPlatformProductId,
        'lowestPrice': lowestPrice.toJson(),
        'platformStats': platformStats.map((e) => e.toJson()).toList(),
        'items': items.map((e) => e.toJson()).toList(),
        'createdAt': createdAt.toIso8601String(),
      };

  /// The item with the best (lowest) price, or null if empty.
  ComparisonItem? get bestItem {
    if (items.isEmpty) return null;
    return items.firstWhere(
      (i) => i.platformProductId == lowestPlatformProductId,
      orElse: () => items.first,
    );
  }

  /// Total number of products across all platforms.
  int get totalProductCount =>
      platformStats.fold(0, (sum, s) => sum + s.productCount);

  /// Total in-stock count across all platforms.
  int get totalInStock =>
      platformStats.fold(0, (sum, s) => sum + s.inStockCount);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ComparisonEntity && comparisonId == other.comparisonId;
  @override
  int get hashCode => comparisonId.hashCode;
}

Map<String, dynamic> _moneyMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  if (value is num || value is String) {
    return {'amount': value, 'currency': 'CNY'};
  }
  return {};
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
