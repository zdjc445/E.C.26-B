/// Raw DTO mirroring the backend JSON for comparison responses.
/// API: POST /api/comparisons
class ComparisonDto {
  final String comparisonId;
  final String searchTaskId;
  final String? lowestPlatformProductId;
  final Map<String, dynamic> lowestPrice;
  final List<Map<String, dynamic>> platformStats;
  final List<Map<String, dynamic>> items;
  final String? createdAt;

  const ComparisonDto({
    required this.comparisonId,
    required this.searchTaskId,
    this.lowestPlatformProductId,
    required this.lowestPrice,
    this.platformStats = const [],
    this.items = const [],
    this.createdAt,
  });

  factory ComparisonDto.fromJson(Map<String, dynamic> json) {
    return ComparisonDto(
      comparisonId: json['comparisonId']?.toString() ?? '',
      searchTaskId: json['searchTaskId']?.toString() ?? '',
      lowestPlatformProductId: json['lowestPlatformProductId']?.toString(),
      lowestPrice: _mapValue(json['lowestPrice']),
      platformStats: (json['platformStats'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList() ??
          const [],
      items: (json['items'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList() ??
          const [],
      createdAt: json['createdAt'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'comparisonId': comparisonId,
        'searchTaskId': searchTaskId,
        'lowestPlatformProductId': lowestPlatformProductId,
        'lowestPrice': lowestPrice,
        'platformStats': platformStats,
        'items': items,
        'createdAt': createdAt,
      };
}

/// Request body for POST /api/comparisons
class CreateComparisonRequest {
  final String searchTaskId;
  final List<String> platformProductIds;

  const CreateComparisonRequest({
    required this.searchTaskId,
    required this.platformProductIds,
  });

  Map<String, dynamic> toJson() => {
        'searchTaskId': int.tryParse(searchTaskId) ?? searchTaskId,
        'platformProductIds':
            platformProductIds.map((id) => int.tryParse(id) ?? id).toList(),
      };
}

Map<String, dynamic> _mapValue(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return {};
}
