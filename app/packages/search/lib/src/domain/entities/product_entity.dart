import 'package:app_core/app_core_domain.dart';

/// Domain entity for a single product search result.
class ProductEntity {
  final String productId;
  final String title;
  final String? imageUrl;
  final double price;
  final double? originalPrice;
  final Platform platform;
  final String? shopName;
  final double? rating;
  final int? reviewCount;
  final int? salesCount;
  final SourceType sourceType;
  final bool officialOnly;
  final bool selfOperatedOnly;
  final String? productUrl;
  final PriceTrend priceTrend;
  final Map<String, dynamic>? extra;

  const ProductEntity({
    required this.productId,
    required this.title,
    this.imageUrl,
    required this.price,
    this.originalPrice,
    required this.platform,
    this.shopName,
    this.rating,
    this.reviewCount,
    this.salesCount,
    this.sourceType = SourceType.mock,
    this.officialOnly = false,
    this.selfOperatedOnly = false,
    this.productUrl,
    this.priceTrend = PriceTrend.unknown,
    this.extra,
  });

  /// Discount percentage (0-100), or 0 if no original price.
  int get discountPercent {
    if (originalPrice == null ||
        originalPrice! <= 0 ||
        price >= originalPrice!) {
      return 0;
    }
    return ((1 - price / originalPrice!) * 100).round();
  }

  String get platformLabel => platform.apiValue;

  factory ProductEntity.fromJson(Map<String, dynamic> json) {
    final originalPrice = json['originalPrice'];
    return ProductEntity(
      productId: (json['platformProductId'] ?? json['productId'] ?? json['id'])
              ?.toString() ??
          '',
      title: json['title'] as String? ?? '',
      imageUrl: json['imageUrl'] as String? ?? json['image'] as String?,
      price: _moneyAmount(json['price']),
      originalPrice: originalPrice == null ? null : _moneyAmount(originalPrice),
      platform: Platform.fromApi(json['platform'] as String? ?? 'other'),
      shopName: json['shopName'] as String? ?? json['shop'] as String?,
      rating: (json['rating'] as num?)?.toDouble(),
      reviewCount: json['reviewCount'] as int? ?? json['reviews'] as int?,
      salesCount: _intValue(
        json['salesCount'] ?? json['sales'] ?? json['salesVolume'],
      ),
      sourceType: SourceType.fromApi(json['sourceType'] as String? ?? 'mock'),
      officialOnly:
          json['officialOnly'] as bool? ?? json['isOfficial'] as bool? ?? false,
      selfOperatedOnly: json['selfOperatedOnly'] as bool? ??
          json['isSelfOperated'] as bool? ??
          false,
      productUrl: json['productUrl'] as String? ?? json['url'] as String?,
      priceTrend:
          PriceTrend.fromApi(json['priceTrend'] as String? ?? 'unknown'),
      extra: json['extra'] == null
          ? {
              if (json['productId'] != null)
                'backendProductId': json['productId'],
              if (json['tags'] != null) 'tags': json['tags'],
              if (json['matchScore'] != null) 'matchScore': json['matchScore'],
              if (json['matchReasons'] != null)
                'matchReasons': json['matchReasons'],
            }
          : Map<String, dynamic>.from(json['extra'] as Map),
    );
  }

  Map<String, dynamic> toJson() => {
        'productId': productId,
        'title': title,
        if (imageUrl != null) 'imageUrl': imageUrl,
        'price': price,
        if (originalPrice != null) 'originalPrice': originalPrice,
        'platform': platform.apiValue,
        if (shopName != null) 'shopName': shopName,
        if (rating != null) 'rating': rating,
        if (reviewCount != null) 'reviewCount': reviewCount,
        if (salesCount != null) 'salesCount': salesCount,
        'sourceType': sourceType.apiValue,
        'officialOnly': officialOnly,
        'selfOperatedOnly': selfOperatedOnly,
        if (productUrl != null) 'productUrl': productUrl,
        'priceTrend': priceTrend.name,
        if (extra != null) 'extra': extra,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ProductEntity &&
          productId == other.productId &&
          platform == other.platform;

  @override
  int get hashCode => Object.hash(productId, platform);
}

double _moneyAmount(Object? value) {
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value) ?? 0.0;
  if (value is Map) return _moneyAmount(value['amount']);
  return 0.0;
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
