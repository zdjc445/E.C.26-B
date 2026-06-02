import 'package:dio/dio.dart';
import 'auth_interceptor.dart';
import 'error_interceptor.dart';
import 'retry_policy.dart';
import '../store/token_store.dart';

/// Creates a pre-configured [Dio] instance with the full interceptor chain:
///   AuthInterceptor  → injects Bearer token, auto-refreshes on 401
///   RetryPolicy      → exponential backoff for transient failures
///   ErrorInterceptor → maps DioException → Failure subclasses
Dio createDio({
  required String baseUrl,
  required TokenStore tokenStore,
  Duration connectTimeout = const Duration(seconds: 10),
  Duration receiveTimeout = const Duration(seconds: 30),
  int maxRetries = 3,
}) {
  final dio = Dio(BaseOptions(
    baseUrl: baseUrl,
    connectTimeout: connectTimeout,
    receiveTimeout: receiveTimeout,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
  ));

  dio.interceptors.addAll([
    AuthInterceptor(dio: dio, tokenStore: tokenStore),
    RetryPolicy(maxRetries: maxRetries, dio: dio),
    ErrorInterceptor(),
  ]);

  return dio;
}
