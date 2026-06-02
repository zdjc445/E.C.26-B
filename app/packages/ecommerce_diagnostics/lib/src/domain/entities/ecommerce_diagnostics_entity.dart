/// Describes a single e-commerce provider's configuration status.
class EcommerceProviderDiagnostic {
  final String platform;
  final bool configured;
  final bool success;
  final String status;
  final int itemCount;
  final int durationMs;
  final List<String> sampleTitles;
  final String? errorCode;
  final String? errorMessage;
  final List<String> missingConfig;

  const EcommerceProviderDiagnostic({
    required this.platform,
    required this.configured,
    required this.success,
    required this.status,
    required this.itemCount,
    required this.durationMs,
    this.sampleTitles = const [],
    this.errorCode,
    this.errorMessage,
    this.missingConfig = const [],
  });

  factory EcommerceProviderDiagnostic.fromJson(Map<String, dynamic> json) {
    return EcommerceProviderDiagnostic(
      platform: json['platform'] as String? ?? 'unknown',
      configured: json['configured'] as bool? ?? false,
      success: json['success'] as bool? ?? false,
      status: json['status'] as String? ?? 'unknown',
      itemCount: json['itemCount'] as int? ?? 0,
      durationMs: json['durationMs'] as int? ?? 0,
      sampleTitles: (json['sampleTitles'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      errorCode: json['errorCode'] as String?,
      errorMessage: json['errorMessage'] as String?,
      missingConfig: (json['missingConfig'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() => {
        'platform': platform,
        'configured': configured,
        'success': success,
        'status': status,
        'itemCount': itemCount,
        'durationMs': durationMs,
        'sampleTitles': sampleTitles,
        'errorCode': errorCode,
        'errorMessage': errorMessage,
        'missingConfig': missingConfig,
      };
}

/// Domain entity for the overall e-commerce diagnostics result.
class EcommerceDiagnosticsEntity {
  final String query;
  final DateTime checkedAt;
  final List<EcommerceProviderDiagnostic> providers;

  const EcommerceDiagnosticsEntity({
    required this.query,
    required this.checkedAt,
    this.providers = const [],
  });

  factory EcommerceDiagnosticsEntity.fromJson(Map<String, dynamic> json) {
    final providersList = (json['providers'] as List<dynamic>?)
            ?.map((e) =>
                EcommerceProviderDiagnostic.fromJson(e as Map<String, dynamic>))
            .toList() ??
        [];
    return EcommerceDiagnosticsEntity(
      query: json['query'] as String? ?? '',
      checkedAt: DateTime.parse(json['checkedAt'] as String),
      providers: providersList,
    );
  }

  Map<String, dynamic> toJson() => {
        'query': query,
        'checkedAt': checkedAt.toIso8601String(),
        'providers': providers.map((p) => p.toJson()).toList(),
      };

  /// Providers that completed successfully with results.
  List<EcommerceProviderDiagnostic> get successfulProviders =>
      providers.where((p) => p.success && p.itemCount > 0).toList();

  /// Providers that were attempted but failed.
  List<EcommerceProviderDiagnostic> get failedProviders =>
      providers.where((p) => p.configured && !p.success).toList();

  /// Providers that are not configured at all.
  List<EcommerceProviderDiagnostic> get unconfiguredProviders =>
      providers.where((p) => !p.configured).toList();
}
