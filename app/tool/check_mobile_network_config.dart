import 'dart:io';

void main() {
  final packageDir = Directory('packages');
  final offenders = <String>[];

  for (final file in packageDir
      .listSync(recursive: true)
      .whereType<File>()
      .where((file) => file.path.endsWith('.dart'))) {
    final normalized = file.path.replaceAll('\\', '/');
    if (normalized.contains('/core/lib/src/network/')) continue;
    if (normalized.contains('/data/datasources/')) continue;
    final source = file.readAsStringSync();
    if (source.contains("baseUrl: 'http://localhost:8080'") ||
        source.contains('baseUrl: "http://localhost:8080"') ||
        source.contains('final _dioProvider = Provider') ||
        source.contains('SecureTokenStore()')) {
      offenders.add(normalized);
    }
  }

  _check(
    offenders.isEmpty,
    'Feature packages must use appDioProvider/sharedTokenStoreProvider: '
    '${offenders.join(', ')}',
  );

  final coreBarrel = File('packages/core/lib/app_core.dart').readAsStringSync();
  _check(
    coreBarrel.contains("export 'src/network/api_client_provider.dart';"),
    'app_core.dart must export api_client_provider.dart',
  );

  final apiProvider =
      File('packages/core/lib/src/network/api_client_provider.dart')
          .readAsStringSync();
  _check(
    apiProvider.contains('EC26B_API_BASE_URL') &&
        apiProvider.contains('appDioProvider') &&
        apiProvider.contains('sharedTokenStoreProvider'),
    'api_client_provider.dart must expose dart-define base URL and shared Dio',
  );

  stdout.writeln('mobile network config ok');
}

void _check(bool condition, String message) {
  if (!condition) {
    throw StateError(message);
  }
}
