import '../../domain/entities/recommendation_entity.dart';
import '../models/recommendation_dto.dart';

/// Maps recommendation DTOs to domain entities.
class RecommendationMapper {
  static RecommendationEntity entityFromDto(RecommendationDto dto) {
    return RecommendationEntity.fromJson({
      'recommendationId': dto.recommendationId,
      'searchTaskId': dto.searchTaskId,
      'suggestion': dto.suggestion,
      'recommendedPlatformProduct': dto.recommendedPlatformProduct,
      'decisionScore': dto.decisionScore,
      'decisionSignals': dto.decisionSignals,
      'decisionTrace': dto.decisionTrace,
      'candidateAnalyses': dto.candidateAnalyses,
      'reasons': dto.reasons,
      'risks': dto.risks,
      'evidence': dto.evidence,
      'createdAt': dto.createdAt,
    });
  }
}
