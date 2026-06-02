import 'package:app_core/app_core_domain.dart';

/// Per-platform search result statistics.
class PlatformStats {
  final Platform platform;
  final int resultCount;
  final double? minPrice;
  final double? maxPrice;
  final double? avgPrice;

  const PlatformStats({
    required this.platform,
    this.resultCount = 0,
    this.minPrice,
    this.maxPrice,
    this.avgPrice,
  });

  factory PlatformStats.fromJson(Map<String, dynamic> json) {
    return PlatformStats(
      platform: Platform.fromApi(json['platform'] as String? ?? 'other'),
      resultCount: _intValue(json['resultCount'] ?? json['productCount']) ?? 0,
      minPrice: _nullableMoneyAmount(json['minPrice'] ?? json['lowestPrice']),
      maxPrice: _nullableMoneyAmount(json['maxPrice'] ?? json['highestPrice']),
      avgPrice: _nullableMoneyAmount(json['avgPrice'] ?? json['averagePrice']),
    );
  }

  Map<String, dynamic> toJson() => {
        'platform': platform.apiValue,
        'resultCount': resultCount,
        if (minPrice != null) 'minPrice': minPrice,
        if (maxPrice != null) 'maxPrice': maxPrice,
        if (avgPrice != null) 'avgPrice': avgPrice,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PlatformStats && platform == other.platform;

  @override
  int get hashCode => platform.hashCode;
}

double? _nullableMoneyAmount(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value);
  if (value is Map) return _nullableMoneyAmount(value['amount']);
  return null;
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
