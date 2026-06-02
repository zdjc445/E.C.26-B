/// Raw DTO mirroring the backend JSON for price history responses.
/// API: GET /api/platform-products/{id}/price-history?days=90
class PriceDto {
  final String platformProductId;
  final int days;
  final double currentPrice;
  final double lowestPrice;
  final double highestPrice;
  final String trend;
  final List<Map<String, dynamic>> points;

  const PriceDto({
    required this.platformProductId,
    required this.days,
    required this.currentPrice,
    required this.lowestPrice,
    required this.highestPrice,
    required this.trend,
    this.points = const [],
  });

  factory PriceDto.fromJson(Map<String, dynamic> json) {
    return PriceDto(
      platformProductId: json['platformProductId']?.toString() ?? '',
      days: _intValue(json['days']) ?? 90,
      currentPrice: _moneyAmount(json['currentPrice']),
      lowestPrice: _moneyAmount(json['lowestPrice']),
      highestPrice: _moneyAmount(json['highestPrice']),
      trend: json['trend'] as String? ?? 'unknown',
      points: (json['points'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
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
        'trend': trend,
        'points': points,
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
