import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/search_task_dto.dart';

/// Calls /api/search-tasks endpoints via Dio.
class SearchRemoteDataSource {
  final Dio _dio;

  SearchRemoteDataSource(this._dio);

  /// POST /api/search-tasks — create a new search task.
  Future<SearchTaskDto> createSearch({
    String? recognitionId,
    String? query,
    List<String>? platforms,
    String? sourceType,
    Map<String, dynamic>? filters,
    String? sortBy,
  }) async {
    final body = <String, dynamic>{};
    if (recognitionId != null) {
      body['recognitionId'] = int.tryParse(recognitionId) ?? recognitionId;
    }
    if (query != null) body['query'] = query;
    if (platforms != null && platforms.isNotEmpty) {
      body['platforms'] = platforms;
    }
    if (sourceType != null) body['sourceType'] = sourceType;
    if (filters != null) body['filters'] = filters;
    if (sortBy != null) body['sortBy'] = sortBy;

    final resp = await _dio.post('/api/search-tasks', data: body);
    final apiResp = ApiResponse<SearchTaskDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          SearchTaskDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  /// POST /api/search-tasks/{id}/refine — refine an existing search.
  Future<SearchTaskDto> refineSearch({
    required String taskId,
    required String text,
    String? sortBy,
  }) async {
    final body = <String, dynamic>{'text': text};
    if (sortBy != null) body['sortBy'] = sortBy;

    final resp =
        await _dio.post('/api/search-tasks/$taskId/refine', data: body);
    final apiResp = ApiResponse<SearchTaskDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          SearchTaskDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  /// GET /api/search-tasks — get paginated search history.
  Future<List<SearchTaskDto>> getSearchHistory({
    int page = 1,
    int pageSize = 20,
  }) async {
    final resp = await _dio.get('/api/search-tasks', queryParameters: {
      'page': page,
      'pageSize': pageSize,
    });
    final apiResp = ApiResponse<List<dynamic>>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) {
        if (node is Map) {
          return List<dynamic>.from(node['items'] as List? ?? const []);
        }
        return List<dynamic>.from(node as List? ?? const []);
      },
    );
    _assertSuccess(apiResp);
    return (apiResp.data ?? [])
        .map((e) => SearchTaskDto.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  void _assertSuccess<T>(ApiResponse<T> resp) {
    if (!resp.isSuccess) {
      throw DioException(
        requestOptions: RequestOptions(path: ''),
        response: Response(
          requestOptions: RequestOptions(path: ''),
          statusCode: resp.code,
          data: {'code': resp.code, 'message': resp.message},
        ),
      );
    }
  }
}
