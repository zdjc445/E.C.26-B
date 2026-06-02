/// Raw DTO for a single provider in the e-commerce status response.
class EcommerceProviderStatusDto {
  final String platform;
  final bool enabled;
  final bool configured;
  final List<String> requiredConfig;
  final List<String> missingConfig;

  const EcommerceProviderStatusDto({
    required this.platform,
    required this.enabled,
    required this.configured,
    this.requiredConfig = const [],
    this.missingConfig = const [],
  });

  factory EcommerceProviderStatusDto.fromJson(Map<String, dynamic> json) {
    return EcommerceProviderStatusDto(
      platform: json['platform'] as String? ?? 'unknown',
      enabled: json['enabled'] as bool? ?? false,
      configured: json['configured'] as bool? ?? false,
      requiredConfig: (json['requiredConfig'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      missingConfig: (json['missingConfig'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() => {
    'platform': platform,
    'enabled': enabled,
    'configured': configured,
    'requiredConfig': requiredConfig,
    'missingConfig': missingConfig,
  };
}

/// Raw DTO for the full e-commerce status response.
class EcommerceStatusDto {
  final bool enabled;
  final bool hasConfiguredClient;
  final List<EcommerceProviderStatusDto> providers;

  const EcommerceStatusDto({
    required this.enabled,
    required this.hasConfiguredClient,
    this.providers = const [],
  });

  factory EcommerceStatusDto.fromJson(Map<String, dynamic> json) {
    final providersList = (json['providers'] as List<dynamic>?)
            ?.map((e) =>
                EcommerceProviderStatusDto.fromJson(e as Map<String, dynamic>))
            .toList() ??
        [];
    return EcommerceStatusDto(
      enabled: json['enabled'] as bool? ?? false,
      hasConfiguredClient: json['hasConfiguredClient'] as bool? ?? false,
      providers: providersList,
    );
  }
}

/// Raw DTO for a single provider diagnostic entry.
class EcommerceProviderDiagnosticDto {
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

  const EcommerceProviderDiagnosticDto({
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

  factory EcommerceProviderDiagnosticDto.fromJson(Map<String, dynamic> json) {
    return EcommerceProviderDiagnosticDto(
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
}

/// Raw DTO for the diagnostics response.
class EcommerceDiagnosticsDto {
  final String query;
  final String checkedAt;
  final List<EcommerceProviderDiagnosticDto> providers;

  const EcommerceDiagnosticsDto({
    required this.query,
    required this.checkedAt,
    this.providers = const [],
  });

  factory EcommerceDiagnosticsDto.fromJson(Map<String, dynamic> json) {
    final providersList = (json['providers'] as List<dynamic>?)
            ?.map((e) => EcommerceProviderDiagnosticDto.fromJson(
                e as Map<String, dynamic>))
            .toList() ??
        [];
    return EcommerceDiagnosticsDto(
      query: json['query'] as String? ?? '',
      checkedAt: json['checkedAt'] as String? ?? DateTime.now().toIso8601String(),
      providers: providersList,
    );
  }
}
