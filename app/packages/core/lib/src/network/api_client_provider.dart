import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../store/token_store.dart';
import 'dio_factory.dart';

const _apiBaseUrlFromEnv = String.fromEnvironment(
  'EC26B_API_BASE_URL',
  defaultValue: 'http://localhost:8080',
);

/// Backend API base URL for the Flutter app.
///
/// Override it at runtime with:
/// `--dart-define=EC26B_API_BASE_URL=http://10.0.2.2:8080`
final apiBaseUrlProvider = Provider<String>(
  (_) => _normalizeBaseUrl(_apiBaseUrlFromEnv),
);

/// Shared token store used by all feature packages.
final sharedTokenStoreProvider = Provider<TokenStore>(
  (_) => SecureTokenStore(),
);

/// Shared Dio instance used by all feature packages.
final appDioProvider = Provider<Dio>((ref) {
  return createDio(
    baseUrl: ref.watch(apiBaseUrlProvider),
    tokenStore: ref.watch(sharedTokenStoreProvider),
  );
});

String _normalizeBaseUrl(String value) {
  final trimmed = value.trim();
  if (trimmed.endsWith('/')) {
    return trimmed.substring(0, trimmed.length - 1);
  }
  return trimmed;
}
