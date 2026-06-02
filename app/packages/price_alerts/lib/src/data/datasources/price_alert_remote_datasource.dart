import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/price_alert_dto.dart';

/// Remote datasource: calls the /api/price-alerts endpoints directly via Dio.
class PriceAlertRemoteDataSource {
  final Dio _dio;

  PriceAlertRemoteDataSource(this._dio);

  /// POST /api/price-alerts
  Future<PriceAlertDto> createAlert({
    required String platformProductId,
    required Map<String, dynamic> targetPrice,
    bool enabled = true,
  }) async {
    final resp = await _dio.post('/api/price-alerts', data: {
      'platformProductId': int.tryParse(platformProductId) ?? platformProductId,
      'targetPrice': targetPrice,
      'enabled': enabled,
    });
    final apiResp = ApiResponse<PriceAlertDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          PriceAlertDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  /// PATCH /api/price-alerts/{priceAlertId}
  Future<PriceAlertDto> updateAlert(
    String priceAlertId, {
    Map<String, dynamic>? targetPrice,
    bool? enabled,
  }) async {
    final body = <String, dynamic>{};
    if (targetPrice != null) body['targetPrice'] = targetPrice;
    if (enabled != null) body['enabled'] = enabled;

    final resp = await _dio.patch(
      '/api/price-alerts/$priceAlertId',
      data: body,
    );
    final apiResp = ApiResponse<PriceAlertDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          PriceAlertDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  /// DELETE /api/price-alerts/{priceAlertId}
  Future<void> deleteAlert(String priceAlertId) async {
    final resp = await _dio.delete('/api/price-alerts/$priceAlertId');
    final apiResp = ApiResponse.fromRawJson(
      resp.data as Map<String, dynamic>,
    );
    _assertSuccess(apiResp);
  }

  /// GET /api/price-alerts?page=1&pageSize=20
  Future<PriceAlertListDto> listAlerts({
    int page = 1,
    int pageSize = 20,
  }) async {
    final resp = await _dio.get('/api/price-alerts', queryParameters: {
      'page': page,
      'pageSize': pageSize,
    });
    final apiResp = ApiResponse<PriceAlertListDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          PriceAlertListDto.fromJson(node as Map<String, dynamic>),
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
