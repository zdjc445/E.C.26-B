/// Raw DTO mirroring the backend JSON for price alert responses.
class PriceAlertDto {
  final String priceAlertId;
  final String platformProductId;
  final String title;
  final Map<String, dynamic> currentPrice;
  final Map<String, dynamic> targetPrice;
  final bool enabled;
  final String createdAt;
  final String updatedAt;

  const PriceAlertDto({
    required this.priceAlertId,
    required this.platformProductId,
    required this.title,
    required this.currentPrice,
    required this.targetPrice,
    required this.enabled,
    required this.createdAt,
    required this.updatedAt,
  });

  factory PriceAlertDto.fromJson(Map<String, dynamic> json) {
    return PriceAlertDto(
      priceAlertId: json['priceAlertId']?.toString() ?? '',
      platformProductId: json['platformProductId']?.toString() ?? '',
      title: json['title'] as String? ?? '',
      currentPrice: _mapValue(json['currentPrice']),
      targetPrice: _mapValue(json['targetPrice']),
      enabled: json['enabled'] as bool? ?? true,
      createdAt:
          json['createdAt'] as String? ?? DateTime.now().toIso8601String(),
      updatedAt:
          json['updatedAt'] as String? ?? DateTime.now().toIso8601String(),
    );
  }

  Map<String, dynamic> toJson() => {
        'priceAlertId': priceAlertId,
        'platformProductId': platformProductId,
        'title': title,
        'currentPrice': currentPrice,
        'targetPrice': targetPrice,
        'enabled': enabled,
        'createdAt': createdAt,
        'updatedAt': updatedAt,
      };
}

/// DTO for the paginated price alerts list response.
class PriceAlertListDto {
  final List<PriceAlertDto> items;
  final int page;
  final int pageSize;
  final int total;

  const PriceAlertListDto({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  factory PriceAlertListDto.fromJson(Map<String, dynamic> json) {
    final itemsList = (json['items'] as List<dynamic>?)
            ?.map((e) => PriceAlertDto.fromJson(e as Map<String, dynamic>))
            .toList() ??
        [];
    return PriceAlertListDto(
      items: itemsList,
      page: _intValue(json['page']) ?? 1,
      pageSize: _intValue(json['pageSize']) ?? 20,
      total: _intValue(json['total']) ?? 0,
    );
  }
}

Map<String, dynamic> _mapValue(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return {};
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
