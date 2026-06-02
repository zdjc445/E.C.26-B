import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/price_dto.dart';
import '../models/review_dto.dart';

/// Remote data source that calls the product inspection endpoints via Dio.
class ProductInspectionRemoteDataSource {
  final Dio _dio;

  ProductInspectionRemoteDataSource(this._dio);

  Future<PriceDto> getPriceHistory({
    required String platformProductId,
    int days = 90,
  }) async {
    final resp = await _dio.get(
      '/api/platform-products/$platformProductId/price-history',
      queryParameters: {'days': days},
    );
    final apiResp = ApiResponse<PriceDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) => PriceDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  Future<ReviewDto> getReviewSummary({
    required String platformProductId,
  }) async {
    final resp = await _dio.get(
      '/api/platform-products/$platformProductId/review-summary',
    );
    final apiResp = ApiResponse<ReviewDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) => ReviewDto.fromJson(node as Map<String, dynamic>),
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
