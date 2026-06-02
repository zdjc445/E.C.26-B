import 'package:app_core/app_core_domain.dart';
import 'filter_criteria.dart';
import 'platform_stats.dart';
import 'product_entity.dart';

/// Domain entity for a search task (one-shot or refinement-based).
class SearchTaskEntity {
  final String taskId;
  final String? recognitionId;
  final String? query;
  final List<Platform> platforms;
  final SourceType sourceType;
  final FilterCriteria? filters;
  final SortMode? sortBy;
  final List<ProductEntity> results;
  final List<PlatformStats> platformStats;
  final int totalResults;
  final String status;
  final DateTime createdAt;

  const SearchTaskEntity({
    required this.taskId,
    this.recognitionId,
    this.query,
    this.platforms = const [],
    this.sourceType = SourceType.mock,
    this.filters,
    this.sortBy,
    this.results = const [],
    this.platformStats = const [],
    this.totalResults = 0,
    this.status = 'completed',
    required this.createdAt,
  });

  factory SearchTaskEntity.fromJson(Map<String, dynamic> json) {
    final resultsRaw = json['items'] as List<dynamic>? ??
        json['results'] as List<dynamic>? ??
        const [];
    final statsRaw = json['platformStats'] as List<dynamic>?;
    final recognition = json['recognition'];
    final recognitionId = json['recognitionId'] ??
        (recognition is Map ? recognition['recognitionId'] : null);
    final platformsRaw = json['platforms'] as List<dynamic>? ??
        resultsRaw
            .map((item) => item is Map ? item['platform'] : null)
            .where((platform) => platform != null)
            .toSet()
            .toList();

    return SearchTaskEntity(
      taskId:
          (json['searchTaskId'] ?? json['taskId'] ?? json['id'])?.toString() ??
              '',
      recognitionId: recognitionId?.toString(),
      query: (json['query'] ?? json['text']) as String?,
      platforms:
          platformsRaw.map((e) => Platform.fromApi(e.toString())).toList(),
      sourceType: SourceType.fromApi(json['sourceType'] as String? ?? 'mock'),
      filters: json['filters'] != null
          ? FilterCriteria.fromJson(
              Map<String, dynamic>.from(json['filters'] as Map))
          : null,
      sortBy: json['sortBy'] != null
          ? SortMode.fromApi(json['sortBy'] as String)
          : null,
      results: resultsRaw
          .map((e) =>
              ProductEntity.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      platformStats: statsRaw
              ?.map((e) =>
                  PlatformStats.fromJson(Map<String, dynamic>.from(e as Map)))
              .toList() ??
          [],
      totalResults: _intValue(json['totalResults'] ?? json['resultCount']) ??
          resultsRaw.length,
      status: json['status'] as String? ?? 'completed',
      createdAt: DateTime.tryParse(json['createdAt'] as String? ?? '') ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'taskId': taskId,
        if (recognitionId != null) 'recognitionId': recognitionId,
        if (query != null) 'query': query,
        'platforms': platforms.map((p) => p.apiValue).toList(),
        'sourceType': sourceType.apiValue,
        'filters': filters?.toJson(),
        if (sortBy != null) 'sortBy': sortBy!.apiValue,
        'results': results.map((p) => p.toJson()).toList(),
        'platformStats': platformStats.map((s) => s.toJson()).toList(),
        'totalResults': totalResults,
        'status': status,
        'createdAt': createdAt.toIso8601String(),
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is SearchTaskEntity && taskId == other.taskId;

  @override
  int get hashCode => taskId.hashCode;
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
