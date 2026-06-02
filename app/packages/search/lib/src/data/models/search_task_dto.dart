/// Raw DTO mirroring the backend JSON for search task responses.
class SearchTaskDto {
  final String taskId;
  final String? recognitionId;
  final String? query;
  final List<dynamic> platforms;
  final String sourceType;
  final Map<String, dynamic>? filters;
  final String? sortBy;
  final List<dynamic> results;
  final List<dynamic> platformStats;
  final int totalResults;
  final String status;
  final String createdAt;

  const SearchTaskDto({
    required this.taskId,
    this.recognitionId,
    this.query,
    this.platforms = const [],
    this.sourceType = 'mock',
    this.filters,
    this.sortBy,
    this.results = const [],
    this.platformStats = const [],
    this.totalResults = 0,
    this.status = 'completed',
    required this.createdAt,
  });

  factory SearchTaskDto.fromJson(Map<String, dynamic> json) {
    final rawResults =
        json['items'] as List? ?? json['results'] as List? ?? const [];
    final recognition = json['recognition'];
    final recognitionId = json['recognitionId'] ??
        (recognition is Map ? recognition['recognitionId'] : null);
    final rawPlatforms = json['platforms'] as List? ??
        rawResults
            .map((item) => item is Map ? item['platform'] : null)
            .where((platform) => platform != null)
            .toSet()
            .toList();

    return SearchTaskDto(
      taskId:
          _stringValue(json['searchTaskId'] ?? json['taskId'] ?? json['id']),
      recognitionId: recognitionId?.toString(),
      query: (json['query'] ?? json['text']) as String?,
      platforms: List<dynamic>.from(rawPlatforms),
      sourceType: json['sourceType'] as String? ?? 'mock',
      filters: json['filters'] == null
          ? null
          : Map<String, dynamic>.from(json['filters'] as Map),
      sortBy: json['sortBy'] as String?,
      results: List<dynamic>.from(rawResults),
      platformStats: List<dynamic>.from(json['platformStats'] as List? ?? []),
      totalResults: _intValue(json['totalResults'] ?? json['resultCount']) ??
          rawResults.length,
      status: json['status'] as String? ?? 'completed',
      createdAt: json['createdAt'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'taskId': taskId,
        if (recognitionId != null) 'recognitionId': recognitionId,
        if (query != null) 'query': query,
        'platforms': platforms,
        'sourceType': sourceType,
        'filters': filters,
        if (sortBy != null) 'sortBy': sortBy,
        'results': results,
        'platformStats': platformStats,
        'totalResults': totalResults,
        'status': status,
        'createdAt': createdAt,
      };
}

String _stringValue(Object? value) {
  if (value == null) return '';
  return value.toString();
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
