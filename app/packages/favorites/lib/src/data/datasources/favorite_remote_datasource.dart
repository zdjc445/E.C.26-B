import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/favorite_dto.dart';

/// Remote datasource: calls the /api/favorites endpoints directly via Dio.
class FavoriteRemoteDataSource {
  final Dio _dio;

  FavoriteRemoteDataSource(this._dio);

  /// POST /api/favorites
  Future<FavoriteDto> addFavorite({
    required String platformProductId,
    String? note,
  }) async {
    final resp = await _dio.post('/api/favorites', data: {
      'platformProductId': int.tryParse(platformProductId) ?? platformProductId,
      if (note != null) 'note': note,
    });
    final apiResp = ApiResponse<FavoriteDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) => FavoriteDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  /// DELETE /api/favorites/{favoriteId}
  Future<void> removeFavorite(String favoriteId) async {
    final resp = await _dio.delete('/api/favorites/$favoriteId');
    final apiResp = ApiResponse.fromRawJson(
      resp.data as Map<String, dynamic>,
    );
    _assertSuccess(apiResp);
  }

  /// GET /api/favorites?page=1&pageSize=20
  Future<FavoriteListDto> listFavorites({
    int page = 1,
    int pageSize = 20,
  }) async {
    final resp = await _dio.get('/api/favorites', queryParameters: {
      'page': page,
      'pageSize': pageSize,
    });
    final apiResp = ApiResponse<FavoriteListDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          FavoriteListDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
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
