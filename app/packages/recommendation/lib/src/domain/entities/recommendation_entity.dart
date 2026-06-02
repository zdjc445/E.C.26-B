import 'package:app_core/app_core_domain.dart';

/// A recommended product with its match score.
class RecommendedPlatformProduct {
  final String platformProductId;
  final String platform;
  final String title;
  final Money price;
  final double matchScore;

  const RecommendedPlatformProduct({
    required this.platformProductId,
    required this.platform,
    required this.title,
    required this.price,
    this.matchScore = 0.0,
  });

  factory RecommendedPlatformProduct.fromJson(Map<String, dynamic> json) {
    return RecommendedPlatformProduct(
      platformProductId: json['platformProductId']?.toString() ?? '',
      platform: json['platform'] as String? ?? '',
      title: json['title'] as String? ?? '',
      price: Money.fromJson(json['price'] as Map<String, dynamic>? ?? {}),
      matchScore: (json['matchScore'] as num?)?.toDouble() ?? 0.0,
    );
  }

  Map<String, dynamic> toJson() => {
        'platformProductId': platformProductId,
        'platform': platform,
        'title': title,
        'price': price.toJson(),
        'matchScore': matchScore,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RecommendedPlatformProduct &&
          platformProductId == other.platformProductId;
  @override
  int get hashCode => platformProductId.hashCode;
}

/// A piece of evidence supporting the recommendation.
class RecommendationEvidence {
  final String type;
  final String platformProductId;
  final String content;

  const RecommendationEvidence({
    required this.type,
    required this.platformProductId,
    required this.content,
  });

  factory RecommendationEvidence.fromJson(Map<String, dynamic> json) {
    return RecommendationEvidence(
      type: json['type'] as String? ?? '',
      platformProductId: json['platformProductId']?.toString() ?? '',
      content: json['content'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'type': type,
        'platformProductId': platformProductId,
        'content': content,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RecommendationEvidence && content == other.content;
  @override
  int get hashCode => content.hashCode;
}

class RecommendationSignal {
  final String key;
  final String label;
  final int score;
  final String explanation;

  const RecommendationSignal({
    required this.key,
    required this.label,
    required this.score,
    required this.explanation,
  });

  factory RecommendationSignal.fromJson(Map<String, dynamic> json) {
    return RecommendationSignal(
      key: json['key'] as String? ?? '',
      label: json['label'] as String? ?? '',
      score: (json['score'] as num?)?.toInt() ?? 0,
      explanation: json['explanation'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'key': key,
        'label': label,
        'score': score,
        'explanation': explanation,
      };
}

class RecommendationTraceStep {
  final String key;
  final String label;
  final String status;
  final int confidence;
  final String observation;

  const RecommendationTraceStep({
    required this.key,
    required this.label,
    required this.status,
    required this.confidence,
    required this.observation,
  });

  factory RecommendationTraceStep.fromJson(Map<String, dynamic> json) {
    return RecommendationTraceStep(
      key: json['key'] as String? ?? '',
      label: json['label'] as String? ?? '',
      status: json['status'] as String? ?? 'done',
      confidence: (json['confidence'] as num?)?.toInt() ?? 0,
      observation: json['observation'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'key': key,
        'label': label,
        'status': status,
        'confidence': confidence,
        'observation': observation,
      };
}

class RecommendationCandidateAnalysis {
  final String platformProductId;
  final String platform;
  final String title;
  final Money price;
  final int rank;
  final int decisionScore;
  final String verdict;
  final List<String> strengths;
  final List<String> weaknesses;

  const RecommendationCandidateAnalysis({
    required this.platformProductId,
    required this.platform,
    required this.title,
    required this.price,
    required this.rank,
    required this.decisionScore,
    required this.verdict,
    this.strengths = const [],
    this.weaknesses = const [],
  });

  factory RecommendationCandidateAnalysis.fromJson(Map<String, dynamic> json) {
    return RecommendationCandidateAnalysis(
      platformProductId: json['platformProductId']?.toString() ?? '',
      platform: json['platform'] as String? ?? '',
      title: json['title'] as String? ?? '',
      price: Money.fromJson(json['price'] as Map<String, dynamic>? ?? {}),
      rank: (json['rank'] as num?)?.toInt() ?? 0,
      decisionScore: (json['decisionScore'] as num?)?.toInt() ?? 0,
      verdict: json['verdict'] as String? ?? 'watch',
      strengths: (json['strengths'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      weaknesses: (json['weaknesses'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
    );
  }

  Map<String, dynamic> toJson() => {
        'platformProductId': platformProductId,
        'platform': platform,
        'title': title,
        'price': price.toJson(),
        'rank': rank,
        'decisionScore': decisionScore,
        'verdict': verdict,
        'strengths': strengths,
        'weaknesses': weaknesses,
      };
}

/// Domain entity for an AI purchase recommendation.
class RecommendationEntity {
  final String recommendationId;
  final String searchTaskId;
  final SuggestionAction suggestion;
  final RecommendedPlatformProduct recommendedPlatformProduct;
  final int decisionScore;
  final List<RecommendationSignal> decisionSignals;
  final List<RecommendationTraceStep> decisionTrace;
  final List<RecommendationCandidateAnalysis> candidateAnalyses;
  final List<String> reasons;
  final List<String> risks;
  final List<RecommendationEvidence> evidence;
  final DateTime createdAt;

  const RecommendationEntity({
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
    required this.createdAt,
  });

  factory RecommendationEntity.fromJson(Map<String, dynamic> json) {
    return RecommendationEntity(
      recommendationId: json['recommendationId']?.toString() ?? '',
      searchTaskId: json['searchTaskId']?.toString() ?? '',
      suggestion:
          SuggestionAction.fromApi(json['suggestion'] as String? ?? 'compare'),
      recommendedPlatformProduct: RecommendedPlatformProduct.fromJson(
        json['recommendedPlatformProduct'] as Map<String, dynamic>? ?? {},
      ),
      decisionScore: (json['decisionScore'] as num?)?.toInt() ?? 0,
      decisionSignals: (json['decisionSignals'] as List<dynamic>?)
              ?.map((e) =>
                  RecommendationSignal.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      decisionTrace: (json['decisionTrace'] as List<dynamic>?)
              ?.map((e) =>
                  RecommendationTraceStep.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      candidateAnalyses: (json['candidateAnalyses'] as List<dynamic>?)
              ?.map((e) => RecommendationCandidateAnalysis.fromJson(
                  e as Map<String, dynamic>))
              .toList() ??
          const [],
      reasons: (json['reasons'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      risks: (json['risks'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      evidence: (json['evidence'] as List<dynamic>?)
              ?.map((e) =>
                  RecommendationEvidence.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      createdAt: json['createdAt'] != null
          ? DateTime.parse(json['createdAt'] as String)
          : DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'recommendationId': recommendationId,
        'searchTaskId': searchTaskId,
        'suggestion': suggestion.name,
        'recommendedPlatformProduct': recommendedPlatformProduct.toJson(),
        'decisionScore': decisionScore,
        'decisionSignals': decisionSignals.map((e) => e.toJson()).toList(),
        'decisionTrace': decisionTrace.map((e) => e.toJson()).toList(),
        'candidateAnalyses': candidateAnalyses.map((e) => e.toJson()).toList(),
        'reasons': reasons,
        'risks': risks,
        'evidence': evidence.map((e) => e.toJson()).toList(),
        'createdAt': createdAt.toIso8601String(),
      };

  /// Human-readable label for the suggestion action.
  String get suggestionLabel {
    return switch (suggestion) {
      SuggestionAction.buy => '建议购买',
      SuggestionAction.wait => '建议观望',
      SuggestionAction.avoid => '建议避开',
      SuggestionAction.compare => '建议对比',
    };
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RecommendationEntity &&
          recommendationId == other.recommendationId;
  @override
  int get hashCode => recommendationId.hashCode;
}
