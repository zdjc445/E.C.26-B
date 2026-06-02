/// Raw DTO mirroring the backend JSON for review summary responses.
/// API: GET /api/platform-products/{id}/review-summary
class ReviewDto {
  final String platformProductId;
  final double rating;
  final int reviewCount;
  final List<dynamic> positiveTags;
  final List<dynamic> riskTags;
  final double riskScore;
  final String summary;

  const ReviewDto({
    required this.platformProductId,
    required this.rating,
    required this.reviewCount,
    this.positiveTags = const [],
    this.riskTags = const [],
    this.riskScore = 0.0,
    this.summary = '',
  });

  factory ReviewDto.fromJson(Map<String, dynamic> json) {
    return ReviewDto(
      platformProductId: json['platformProductId']?.toString() ?? '',
      rating: (json['rating'] as num?)?.toDouble() ?? 0.0,
      reviewCount: _intValue(json['reviewCount']) ?? 0,
      positiveTags: (json['positiveTags'] as List<dynamic>?) ?? const [],
      riskTags: (json['riskTags'] as List<dynamic>?) ?? const [],
      riskScore: (json['riskScore'] as num?)?.toDouble() ?? 0.0,
      summary: json['summary'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'platformProductId': platformProductId,
        'rating': rating,
        'reviewCount': reviewCount,
        'positiveTags': positiveTags,
        'riskTags': riskTags,
        'riskScore': riskScore,
        'summary': summary,
      };
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
