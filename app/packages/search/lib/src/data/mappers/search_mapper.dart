import 'package:app_core/app_core.dart';
import '../../domain/entities/search_task_entity.dart';
import '../../domain/entities/product_entity.dart';
import '../../domain/entities/filter_criteria.dart';
import '../../domain/entities/platform_stats.dart';
import '../models/search_task_dto.dart';

/// Maps SearchTaskDto to domain SearchTaskEntity and vice versa.
class SearchMapper {
  static SearchTaskEntity fromDto(SearchTaskDto dto) {
    return SearchTaskEntity(
      taskId: dto.taskId,
      recognitionId: dto.recognitionId,
      query: dto.query,
      platforms: dto.platforms
          .map((e) => Platform.fromApi(e.toString()))
          .toList(),
      sourceType: SourceType.fromApi(dto.sourceType),
      filters: dto.filters != null
          ? FilterCriteria.fromJson(dto.filters!)
          : null,
      sortBy:
          dto.sortBy != null ? SortMode.fromApi(dto.sortBy!) : null,
      results: dto.results
          .map((e) => ProductEntity.fromJson(e as Map<String, dynamic>))
          .toList(),
      platformStats: dto.platformStats
          .map((e) => PlatformStats.fromJson(e as Map<String, dynamic>))
          .toList(),
      totalResults: dto.totalResults,
      status: dto.status,
      createdAt: DateTime.tryParse(dto.createdAt) ?? DateTime.now(),
    );
  }

  static SearchTaskDto toDto(SearchTaskEntity entity) {
    return SearchTaskDto(
      taskId: entity.taskId,
      recognitionId: entity.recognitionId,
      query: entity.query,
      platforms: entity.platforms.map((p) => p.apiValue).toList(),
      sourceType: entity.sourceType.apiValue,
      filters: entity.filters?.toJson(),
      sortBy: entity.sortBy?.apiValue,
      results: entity.results.map((p) => p.toJson()).toList(),
      platformStats: entity.platformStats.map((s) => s.toJson()).toList(),
      totalResults: entity.totalResults,
      status: entity.status,
      createdAt: entity.createdAt.toIso8601String(),
    );
  }

  static List<SearchTaskEntity> fromDtoList(List<SearchTaskDto> dtos) {
    return dtos.map((d) => fromDto(d)).toList();
  }
}
