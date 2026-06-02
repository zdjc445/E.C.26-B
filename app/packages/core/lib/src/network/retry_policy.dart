import 'dart:math';
import 'package:dio/dio.dart';

/// Interceptor that retries failed requests with exponential backoff.
/// Only retries on network-level errors (connection timeout, no internet) —
/// server errors (4xx/5xx) are NOT retried, except 429 (rate limit) and 503.
class RetryPolicy extends Interceptor {
  final int maxRetries;
  final Dio dio;

  RetryPolicy({this.maxRetries = 3, required this.dio});

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (!_shouldRetry(err) || (err.requestOptions.extra['_retryCount'] as int? ?? 0) >= maxRetries) {
      return handler.next(err);
    }

    final retryCount = (err.requestOptions.extra['_retryCount'] as int? ?? 0) + 1;
    final delay = _backoff(retryCount);

    await Future.delayed(delay);

    try {
      final opts = err.requestOptions;
      opts.extra['_retryCount'] = retryCount;
      final response = await dio.fetch(opts);
      handler.resolve(response);
    } on DioException catch (e) {
      // Recurse — the interceptor will see this on the next error event.
      handler.next(e);
    }
  }

  bool _shouldRetry(DioException err) {
    // Retry on connection issues.
    if (err.type == DioExceptionType.connectionTimeout ||
        err.type == DioExceptionType.sendTimeout ||
        err.type == DioExceptionType.receiveTimeout ||
        err.type == DioExceptionType.connectionError) {
      return true;
    }
    // Retry on 429 and 503.
    final code = err.response?.statusCode;
    return code == 429 || code == 503;
  }

  Duration _backoff(int retryCount) {
    // Exponential backoff with jitter: 200ms → 400ms → 800ms → ...
    final base = 200 * pow(2, retryCount - 1);
    final jitter = Random().nextInt(200);
    return Duration(milliseconds: base.toInt() + jitter);
  }
}
