import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/ecommerce_dto.dart';

/// Remote datasource: calls the /api/ecommerce endpoints directly via Dio.
class EcommerceRemoteDataSource {
  final Dio _dio;

  EcommerceRemoteDataSource(this._dio);

  /// GET /api/ecommerce/status (no auth)
  Future<EcommerceStatusDto> getStatus() async {
    final resp = await _dio.get('/api/ecommerce/status');
    final apiResp = ApiResponse<EcommerceStatusDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          EcommerceStatusDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  /// GET /api/ecommerce/diagnostics?query=&pageSize=3&platforms=pdd
  Future<EcommerceDiagnosticsDto> runDiagnostics({
    String query = '',
    int pageSize = 3,
    String? platforms,
  }) async {
    final queryParams = <String, dynamic>{
      'query': query,
      'pageSize': pageSize,
    };
    if (platforms != null && platforms.isNotEmpty) {
      queryParams['platforms'] = platforms;
    }

    final resp = await _dio.get(
      '/api/ecommerce/diagnostics',
      queryParameters: queryParams,
    );
    final apiResp = ApiResponse<EcommerceDiagnosticsDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          EcommerceDiagnosticsDto.fromJson(node as Map<String, dynamic>),
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
