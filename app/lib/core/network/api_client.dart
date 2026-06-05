import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Backend API base URL, overridable at build time via:
/// `--dart-define=EC26B_API_BASE_URL=http://10.0.2.2:8080`
const _apiBaseUrlFromEnv = String.fromEnvironment(
  'EC26B_API_BASE_URL',
  defaultValue: 'http://localhost:8080',
);

/// Provider that exposes the backend base URL throughout the app.
final apiBaseUrlProvider = Provider<String>(
  (_) => _normalizeBaseUrl(_apiBaseUrlFromEnv),
);

String _normalizeBaseUrl(String value) {
  final trimmed = value.trim();
  if (trimmed.endsWith('/')) {
    return trimmed.substring(0, trimmed.length - 1);
  }
  return trimmed;
}
