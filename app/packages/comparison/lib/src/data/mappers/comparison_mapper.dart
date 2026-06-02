import '../../domain/entities/comparison_entity.dart';
import '../models/comparison_dto.dart';

/// Maps comparison DTOs to domain entities.
class ComparisonMapper {
  static ComparisonEntity entityFromDto(ComparisonDto dto) {
    return ComparisonEntity.fromJson({
      'comparisonId': dto.comparisonId,
      'searchTaskId': dto.searchTaskId,
      'lowestPlatformProductId': dto.lowestPlatformProductId,
      'lowestPrice': dto.lowestPrice,
      'platformStats': dto.platformStats,
      'items': dto.items,
      'createdAt': dto.createdAt,
    });
  }
}
