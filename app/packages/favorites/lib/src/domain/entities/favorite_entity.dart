import 'package:app_core/app_core_domain.dart';

/// Domain entity representing a favorited product.
class FavoriteEntity {
  final String favoriteId;
  final String platformProductId;
  final String platform;
  final String title;
  final Money price;
  final String? note;
  final DateTime createdAt;

  const FavoriteEntity({
    required this.favoriteId,
    required this.platformProductId,
    required this.platform,
    required this.title,
    required this.price,
    this.note,
    required this.createdAt,
  });

  factory FavoriteEntity.fromJson(Map<String, dynamic> json) {
    return FavoriteEntity(
      favoriteId: json['favoriteId']?.toString() ?? '',
      platformProductId: json['platformProductId']?.toString() ?? '',
      platform: json['platform'] as String? ?? 'unknown',
      title: json['title'] as String? ?? '',
      price: Money.fromJson(_moneyMap(json['price'])),
      note: json['note'] as String?,
      createdAt: DateTime.tryParse(json['createdAt'] as String? ?? '') ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'favoriteId': favoriteId,
        'platformProductId': platformProductId,
        'platform': platform,
        'title': title,
        'price': price.toJson(),
        'note': note,
        'createdAt': createdAt.toIso8601String(),
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is FavoriteEntity && favoriteId == other.favoriteId;

  @override
  int get hashCode => favoriteId.hashCode;

  @override
  String toString() =>
      'FavoriteEntity($favoriteId, $title, ${price.amount} ${price.currency})';
}

Map<String, dynamic> _moneyMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  if (value is num || value is String) {
    return {'amount': value, 'currency': 'CNY'};
  }
  return {};
}
