/// Raw DTO mirroring the backend JSON for a product in search results.
class ProductDto {
  final String productId;
  final String title;
  final String? imageUrl;
  final double price;
  final double? originalPrice;
  final String platform;
  final String? shopName;
  final double? rating;
  final int? reviewCount;
  final int? salesCount;
  final String sourceType;
  final bool officialOnly;
  final bool selfOperatedOnly;
  final String? productUrl;
  final String priceTrend;
  final Map<String, dynamic>? extra;

  const ProductDto({
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
    this.sourceType = 'mock',
    this.officialOnly = false,
    this.selfOperatedOnly = false,
    this.productUrl,
    this.priceTrend = 'unknown',
    this.extra,
  });

  factory ProductDto.fromJson(Map<String, dynamic> json) {
    final platformProductId =
        json['platformProductId'] ?? json['productId'] ?? json['id'];
    final originalPrice = json['originalPrice'];

    return ProductDto(
      productId: platformProductId?.toString() ?? '',
      title: json['title'] as String? ?? '',
      imageUrl: json['imageUrl'] as String? ?? json['image'] as String?,
      price: _moneyAmount(json['price']),
      originalPrice: originalPrice == null ? null : _moneyAmount(originalPrice),
      platform: json['platform'] as String? ?? 'other',
      shopName: json['shopName'] as String? ?? json['shop'] as String?,
      rating: (json['rating'] as num?)?.toDouble(),
      reviewCount: json['reviewCount'] as int? ?? json['reviews'] as int?,
      salesCount: _intValue(
        json['salesCount'] ?? json['sales'] ?? json['salesVolume'],
      ),
      sourceType: json['sourceType'] as String? ?? 'mock',
      officialOnly:
          json['officialOnly'] as bool? ?? json['isOfficial'] as bool? ?? false,
      selfOperatedOnly: json['selfOperatedOnly'] as bool? ??
          json['isSelfOperated'] as bool? ??
          false,
      productUrl: json['productUrl'] as String? ?? json['url'] as String?,
      priceTrend: json['priceTrend'] as String? ?? 'unknown',
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
        'platform': platform,
        if (shopName != null) 'shopName': shopName,
        if (rating != null) 'rating': rating,
        if (reviewCount != null) 'reviewCount': reviewCount,
        if (salesCount != null) 'salesCount': salesCount,
        'sourceType': sourceType,
        'officialOnly': officialOnly,
        'selfOperatedOnly': selfOperatedOnly,
        if (productUrl != null) 'productUrl': productUrl,
        'priceTrend': priceTrend,
        if (extra != null) 'extra': extra,
      };
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
