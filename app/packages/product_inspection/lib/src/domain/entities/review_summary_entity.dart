/// Domain entity for a product's review summary and risk analysis.
class ReviewSummaryEntity {
  final String platformProductId;
  final double rating;
  final int reviewCount;
  final List<String> positiveTags;
  final List<String> riskTags;
  final double riskScore;
  final String summary;

  const ReviewSummaryEntity({
    required this.platformProductId,
    required this.rating,
    required this.reviewCount,
    this.positiveTags = const [],
    this.riskTags = const [],
    this.riskScore = 0.0,
    this.summary = '',
  });

  factory ReviewSummaryEntity.fromJson(Map<String, dynamic> json) {
    return ReviewSummaryEntity(
      platformProductId: json['platformProductId']?.toString() ?? '',
      rating: (json['rating'] as num?)?.toDouble() ?? 0.0,
      reviewCount: _intValue(json['reviewCount']) ?? 0,
      positiveTags: (json['positiveTags'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      riskTags: (json['riskTags'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
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

  /// A percentage 0-100 for display.
  double get riskPercent => (riskScore * 100).clamp(0, 100);

  /// Whether the product has notable risks.
  bool get hasRisks => riskScore > 0.3 || riskTags.isNotEmpty;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ReviewSummaryEntity &&
          platformProductId == other.platformProductId;
  @override
  int get hashCode => platformProductId.hashCode;
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
