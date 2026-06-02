import 'package:app_core/app_core_domain.dart';

/// Domain entity representing a price alert.
class PriceAlertEntity {
  final String priceAlertId;
  final String platformProductId;
  final String title;
  final Money currentPrice;
  final Money targetPrice;
  final bool enabled;
  final DateTime createdAt;
  final DateTime updatedAt;

  const PriceAlertEntity({
    required this.priceAlertId,
    required this.platformProductId,
    required this.title,
    required this.currentPrice,
    required this.targetPrice,
    required this.enabled,
    required this.createdAt,
    required this.updatedAt,
  });

  factory PriceAlertEntity.fromJson(Map<String, dynamic> json) {
    return PriceAlertEntity(
      priceAlertId: json['priceAlertId']?.toString() ?? '',
      platformProductId: json['platformProductId']?.toString() ?? '',
      title: json['title'] as String? ?? '',
      currentPrice: Money.fromJson(_moneyMap(json['currentPrice'])),
      targetPrice: Money.fromJson(_moneyMap(json['targetPrice'])),
      enabled: json['enabled'] as bool? ?? true,
      createdAt: DateTime.tryParse(json['createdAt'] as String? ?? '') ??
          DateTime.now(),
      updatedAt: DateTime.tryParse(json['updatedAt'] as String? ?? '') ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'priceAlertId': priceAlertId,
        'platformProductId': platformProductId,
        'title': title,
        'currentPrice': currentPrice.toJson(),
        'targetPrice': targetPrice.toJson(),
        'enabled': enabled,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
      };

  /// Whether the current price is at or below the target price (alert triggered).
  bool get isTriggered =>
      currentPrice.amountAsDouble <= targetPrice.amountAsDouble &&
      currentPrice.amountAsDouble > 0;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PriceAlertEntity && priceAlertId == other.priceAlertId;

  @override
  int get hashCode => priceAlertId.hashCode;

  @override
  String toString() =>
      'PriceAlertEntity($priceAlertId, $title, target=${targetPrice.amount}, enabled=$enabled)';
}

Map<String, dynamic> _moneyMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  if (value is num || value is String) {
    return {'amount': value, 'currency': 'CNY'};
  }
  return {};
}
