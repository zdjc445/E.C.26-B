/// Raw DTO mirroring the backend JSON for recommendation responses.
/// API: POST /api/agent/recommendations
class RecommendationDto {
  final String recommendationId;
  final String searchTaskId;
  final String suggestion;
  final Map<String, dynamic> recommendedPlatformProduct;
  final int decisionScore;
  final List<Map<String, dynamic>> decisionSignals;
  final List<Map<String, dynamic>> decisionTrace;
  final List<Map<String, dynamic>> candidateAnalyses;
  final List<dynamic> reasons;
  final List<dynamic> risks;
  final List<Map<String, dynamic>> evidence;
  final String? createdAt;

  const RecommendationDto({
    required this.recommendationId,
    required this.searchTaskId,
    required this.suggestion,
    required this.recommendedPlatformProduct,
    this.decisionScore = 0,
    this.decisionSignals = const [],
    this.decisionTrace = const [],
    this.candidateAnalyses = const [],
    this.reasons = const [],
    this.risks = const [],
    this.evidence = const [],
    this.createdAt,
  });

  factory RecommendationDto.fromJson(Map<String, dynamic> json) {
    return RecommendationDto(
      recommendationId: json['recommendationId']?.toString() ?? '',
      searchTaskId: json['searchTaskId']?.toString() ?? '',
      suggestion: json['suggestion'] as String? ?? 'compare',
      recommendedPlatformProduct:
          (json['recommendedPlatformProduct'] as Map<String, dynamic>?) ?? {},
      decisionScore: (json['decisionScore'] as num?)?.toInt() ?? 0,
      decisionSignals: (json['decisionSignals'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList() ??
          const [],
      decisionTrace: (json['decisionTrace'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList() ??
          const [],
      candidateAnalyses: (json['candidateAnalyses'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList() ??
          const [],
      reasons: (json['reasons'] as List<dynamic>?) ?? const [],
      risks: (json['risks'] as List<dynamic>?) ?? const [],
      evidence: (json['evidence'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList() ??
          const [],
      createdAt: json['createdAt'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'recommendationId': recommendationId,
        'searchTaskId': searchTaskId,
        'suggestion': suggestion,
        'recommendedPlatformProduct': recommendedPlatformProduct,
        'decisionScore': decisionScore,
        'decisionSignals': decisionSignals,
        'decisionTrace': decisionTrace,
        'candidateAnalyses': candidateAnalyses,
        'reasons': reasons,
        'risks': risks,
        'evidence': evidence,
        'createdAt': createdAt,
      };
}

/// Request body for POST /api/agent/recommendations
class CreateRecommendationRequest {
  final String searchTaskId;
  final String userQuery;
  final List<String> candidateIds;

  const CreateRecommendationRequest({
    required this.searchTaskId,
    required this.userQuery,
    required this.candidateIds,
  });

  Map<String, dynamic> toJson() => {
        'searchTaskId': int.tryParse(searchTaskId) ?? searchTaskId,
        'userQuery': userQuery,
        'candidateIds':
            candidateIds.map((id) => int.tryParse(id) ?? id).toList(),
      };
}
