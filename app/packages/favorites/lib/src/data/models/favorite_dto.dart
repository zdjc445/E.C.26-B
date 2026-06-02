/// Raw DTO mirroring the backend JSON for favorites responses.
class FavoriteDto {
  final String favoriteId;
  final String platformProductId;
  final String platform;
  final String title;
  final Map<String, dynamic> price;
  final String? note;
  final String createdAt;

  const FavoriteDto({
    required this.favoriteId,
    required this.platformProductId,
    required this.platform,
    required this.title,
    required this.price,
    this.note,
    required this.createdAt,
  });

  factory FavoriteDto.fromJson(Map<String, dynamic> json) {
    return FavoriteDto(
      favoriteId: json['favoriteId']?.toString() ?? '',
      platformProductId: json['platformProductId']?.toString() ?? '',
      platform: json['platform'] as String? ?? 'unknown',
      title: json['title'] as String? ?? '',
      price: _mapValue(json['price']),
      note: json['note'] as String?,
      createdAt:
          json['createdAt'] as String? ?? DateTime.now().toIso8601String(),
    );
  }

  Map<String, dynamic> toJson() => {
        'favoriteId': favoriteId,
        'platformProductId': platformProductId,
        'platform': platform,
        'title': title,
        'price': price,
        'note': note,
        'createdAt': createdAt,
      };
}

/// DTO for the paginated favorites list response.
class FavoriteListDto {
  final List<FavoriteDto> items;
  final int page;
  final int pageSize;
  final int total;

  const FavoriteListDto({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });

  factory FavoriteListDto.fromJson(Map<String, dynamic> json) {
    final itemsList = (json['items'] as List<dynamic>?)
            ?.map((e) => FavoriteDto.fromJson(e as Map<String, dynamic>))
            .toList() ??
        [];
    return FavoriteListDto(
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
