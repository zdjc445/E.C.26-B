import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/recommendation_dto.dart';

/// Remote data source that calls /api/agent/recommendations via Dio.
class RecommendationRemoteDataSource {
  final Dio _dio;

  RecommendationRemoteDataSource(this._dio);

  Future<RecommendationDto> createRecommendation(
    CreateRecommendationRequest request,
  ) async {
    final resp = await _dio.post(
      '/api/agent/recommendations',
      data: request.toJson(),
    );
    final apiResp = ApiResponse<RecommendationDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          RecommendationDto.fromJson(node as Map<String, dynamic>),
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
