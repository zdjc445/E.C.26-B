import 'package:app_core/app_core_domain.dart';

/// A single price data point recorded at a specific time.
class PricePoint {
  final DateTime recordedAt;
  final double price;

  const PricePoint({required this.recordedAt, required this.price});

  factory PricePoint.fromJson(Map<String, dynamic> json) {
    return PricePoint(
      recordedAt: DateTime.tryParse(json['recordedAt'] as String? ?? '') ??
          DateTime.now(),
      price: _moneyAmount(json['price']),
    );
  }

  Map<String, dynamic> toJson() => {
        'recordedAt': recordedAt.toIso8601String(),
        'price': price,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PricePoint &&
          recordedAt == other.recordedAt &&
          price == other.price;
  @override
  int get hashCode => Object.hash(recordedAt, price);
}

/// Domain entity for a product's price history over a time window.
class PriceHistoryEntity {
  final String platformProductId;
  final int days;
  final double currentPrice;
  final double lowestPrice;
  final double highestPrice;
  final PriceTrend trend;
  final List<PricePoint> points;

  const PriceHistoryEntity({
    required this.platformProductId,
    required this.days,
    required this.currentPrice,
    required this.lowestPrice,
    required this.highestPrice,
    required this.trend,
    this.points = const [],
  });

  factory PriceHistoryEntity.fromJson(Map<String, dynamic> json) {
    return PriceHistoryEntity(
      platformProductId: json['platformProductId']?.toString() ?? '',
      days: _intValue(json['days']) ?? 90,
      currentPrice: _moneyAmount(json['currentPrice']),
      lowestPrice: _moneyAmount(json['lowestPrice']),
      highestPrice: _moneyAmount(json['highestPrice']),
      trend: PriceTrend.fromApi(json['trend'] as String? ?? 'unknown'),
      points: (json['points'] as List<dynamic>?)
              ?.map((p) => PricePoint.fromJson(p as Map<String, dynamic>))
              .toList() ??
          const [],
    );
  }

  Map<String, dynamic> toJson() => {
        'platformProductId': platformProductId,
        'days': days,
        'currentPrice': currentPrice,
        'lowestPrice': lowestPrice,
        'highestPrice': highestPrice,
        'trend': trend.name,
        'points': points.map((p) => p.toJson()).toList(),
      };

  /// Human-readable trend label.
  String get trendLabel {
    return switch (trend) {
      PriceTrend.low => '低位',
      PriceTrend.normal => '正常',
      PriceTrend.high => '高位',
      PriceTrend.unknown => '未知',
    };
  }

  /// Percentage from lowest to highest (0-100 where current sits).
  double get positionInRange {
    final range = highestPrice - lowestPrice;
    if (range <= 0) return 50;
    return ((currentPrice - lowestPrice) / range * 100).clamp(0, 100);
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PriceHistoryEntity &&
          platformProductId == other.platformProductId;
  @override
  int get hashCode => platformProductId.hashCode;
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
