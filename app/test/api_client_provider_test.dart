import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('appDioProvider uses the configured API base URL and shared token store',
      () {
    final tokenStore = _MemoryTokenStore();
    final container = ProviderContainer(
      overrides: [
        apiBaseUrlProvider.overrideWithValue('http://10.0.2.2:8080'),
        sharedTokenStoreProvider.overrideWithValue(tokenStore),
      ],
    );
    addTearDown(container.dispose);

    final dio = container.read(appDioProvider);

    expect(dio.options.baseUrl, 'http://10.0.2.2:8080');
    expect(container.read(sharedTokenStoreProvider), same(tokenStore));
  });
}

class _MemoryTokenStore implements TokenStore {
  String? _accessToken;
  String? _refreshToken;

  @override
  Future<void> clear() async {
    _accessToken = null;
    _refreshToken = null;
  }

  @override
  Future<String?> getAccessToken() async => _accessToken;

  @override
  Future<String?> getRefreshToken() async => _refreshToken;

  @override
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
  }
}
