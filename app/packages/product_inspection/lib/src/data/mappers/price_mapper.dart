import '../../domain/entities/price_history_entity.dart';
import '../../domain/entities/review_summary_entity.dart';
import '../models/price_dto.dart';
import '../models/review_dto.dart';

/// Maps inspection DTOs to domain entities.
class PriceMapper {
  static PriceHistoryEntity priceHistoryFromDto(PriceDto dto) {
    return PriceHistoryEntity.fromJson({
      'platformProductId': dto.platformProductId,
      'days': dto.days,
      'currentPrice': dto.currentPrice,
      'lowestPrice': dto.lowestPrice,
      'highestPrice': dto.highestPrice,
      'trend': dto.trend,
      'points': dto.points,
    });
  }

  static ReviewSummaryEntity reviewSummaryFromDto(ReviewDto dto) {
    return ReviewSummaryEntity.fromJson({
      'platformProductId': dto.platformProductId,
      'rating': dto.rating,
      'reviewCount': dto.reviewCount,
      'positiveTags': dto.positiveTags,
      'riskTags': dto.riskTags,
      'riskScore': dto.riskScore,
      'summary': dto.summary,
    });
  }
}
