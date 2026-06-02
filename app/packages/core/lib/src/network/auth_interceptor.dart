import 'dart:async';
import 'package:dio/dio.dart';
import '../store/token_store.dart';

/// Interceptor that:
///   1. Attaches `Authorization: Bearer <accessToken>` to every request.
///   2. On 401, attempts a single token refresh via the stored refresh token.
///   3. If refresh succeeds, retries the original request with the new token.
///   4. If refresh fails, clears tokens (triggering a login redirect downstream).
class AuthInterceptor extends Interceptor {
  final Dio dio;
  final TokenStore tokenStore;

  /// Set to true while a refresh is in-flight to avoid concurrent refresh races.
  bool _isRefreshing = false;
  final _pendingRequests = <({RequestOptions options, ErrorInterceptorHandler handler})>[];

  AuthInterceptor({required this.dio, required this.tokenStore});

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final token = await tokenStore.getAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode != 401) {
      return handler.next(err);
    }

    // Don't try to refresh if the failing request was itself a refresh call.
    if (err.requestOptions.path.contains('/auth/refresh')) {
      await tokenStore.clear();
      return handler.next(err);
    }

    if (_isRefreshing) {
      // Queue this request; it will be retried after the in-flight refresh completes.
      _pendingRequests.add((options: err.requestOptions, handler: handler));
      return;
    }

    _isRefreshing = true;
    try {
      final newTokens = await _performRefresh();
      if (newTokens != null) {
        // Retry the original request with the new access token.
        final opts = err.requestOptions;
        opts.headers['Authorization'] = 'Bearer ${newTokens.accessToken}';
        final response = await dio.fetch(opts);
        handler.resolve(response);

        // Retry all queued requests.
        for (final pending in _pendingRequests) {
          pending.options.headers['Authorization'] = 'Bearer ${newTokens.accessToken}';
          dio.fetch(pending.options).then(
            (r) => pending.handler.resolve(r),
            onError: (e) => pending.handler.reject(e as DioException),
          );
        }
      } else {
        // Refresh failed — clear tokens, let downstream handle auth failure.
        await tokenStore.clear();
        handler.next(err);
        for (final pending in _pendingRequests) {
          pending.handler.next(err);
        }
      }
    } catch (_) {
      await tokenStore.clear();
      handler.next(err);
      for (final pending in _pendingRequests) {
        pending.handler.next(err);
      }
    } finally {
      _isRefreshing = false;
      _pendingRequests.clear();
    }
  }

  /// Calls POST /api/auth/refresh with the stored refresh token.
  /// Returns `null` if refresh is not possible or fails.
  Future<({String accessToken, String refreshToken})?> _performRefresh() async {
    final refreshToken = await tokenStore.getRefreshToken();
    if (refreshToken == null) return null;

    try {
      // Use a separate Dio instance (no auth interceptor) to avoid loops.
      final refreshDio = Dio(BaseOptions(
        baseUrl: dio.options.baseUrl,
        connectTimeout: const Duration(seconds: 5),
      ));
      final response = await refreshDio.post(
        '/api/auth/refresh',
        data: {'refreshToken': refreshToken},
      );
      final data = response.data?['data'];
      if (data == null) return null;

      final newAccess = data['accessToken'] as String;
      final newRefresh = data['refreshToken'] as String;
      await tokenStore.saveTokens(accessToken: newAccess, refreshToken: newRefresh);
      return (accessToken: newAccess, refreshToken: newRefresh);
    } catch (_) {
      return null;
    }
  }
}
