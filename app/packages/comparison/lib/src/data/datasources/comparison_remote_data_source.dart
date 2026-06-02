import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/comparison_dto.dart';

/// Remote data source that calls the /api/comparisons endpoint via Dio.
class ComparisonRemoteDataSource {
  final Dio _dio;

  ComparisonRemoteDataSource(this._dio);

  Future<ComparisonDto> createComparison(
    CreateComparisonRequest request,
  ) async {
    final resp = await _dio.post(
      '/api/comparisons',
      data: request.toJson(),
    );
    final apiResp = ApiResponse<ComparisonDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          ComparisonDto.fromJson(node as Map<String, dynamic>),
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
