import 'package:dio/dio.dart';
import '../failure.dart';

/// Maps [DioException] into the appropriate [Failure] subclass so that
/// UseCases and Repositories never see raw Dio errors.
class ErrorInterceptor extends Interceptor {
  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    handler.next(err);
  }
}

/// Converts a [DioException] to a typed [Failure].
/// Call this from repository implementations when catching Dio errors.
Failure mapDioError(DioException err) {
  // Network-level issues.
  if (err.type == DioExceptionType.connectionTimeout ||
      err.type == DioExceptionType.sendTimeout ||
      err.type == DioExceptionType.receiveTimeout ||
      err.type == DioExceptionType.connectionError) {
    return NetworkFailure(err.message ?? '网络连接失败，请检查网络后重试');
  }

  // Server returned a response.
  if (err.response != null) {
    final statusCode = err.response!.statusCode ?? -1;
    final data = err.response!.data;
    final message = data is Map
        ? (data['message'] as String? ?? '服务器错误')
        : '服务器错误';
    final code = data is Map
        ? (data['code'] as int? ?? statusCode)
        : statusCode;

    if (statusCode == 401) {
      return AuthFailure(message);
    }

    return ServerFailure(code, message);
  }

  // Unexpected / unknown.
  return UnexpectedFailure(err.message ?? '未知错误');
}
