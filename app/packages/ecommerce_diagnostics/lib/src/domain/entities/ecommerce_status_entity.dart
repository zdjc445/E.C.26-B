/// Describes a single e-commerce provider's configuration status within the
/// overall status endpoint.
class EcommerceProviderStatus {
  final String platform;
  final bool enabled;
  final bool configured;
  final List<String> requiredConfig;
  final List<String> missingConfig;

  const EcommerceProviderStatus({
    required this.platform,
    required this.enabled,
    required this.configured,
    this.requiredConfig = const [],
    this.missingConfig = const [],
  });

  factory EcommerceProviderStatus.fromJson(Map<String, dynamic> json) {
    return EcommerceProviderStatus(
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

/// Domain entity for the overall e-commerce status response.
class EcommerceStatusEntity {
  final bool enabled;
  final bool hasConfiguredClient;
  final List<EcommerceProviderStatus> providers;

  const EcommerceStatusEntity({
    required this.enabled,
    required this.hasConfiguredClient,
    this.providers = const [],
  });

  factory EcommerceStatusEntity.fromJson(Map<String, dynamic> json) {
    final providersList = (json['providers'] as List<dynamic>?)
            ?.map(
                (e) => EcommerceProviderStatus.fromJson(e as Map<String, dynamic>))
            .toList() ??
        [];
    return EcommerceStatusEntity(
      enabled: json['enabled'] as bool? ?? false,
      hasConfiguredClient: json['hasConfiguredClient'] as bool? ?? false,
      providers: providersList,
    );
  }

  Map<String, dynamic> toJson() => {
    'enabled': enabled,
    'hasConfiguredClient': hasConfiguredClient,
    'providers': providers.map((p) => p.toJson()).toList(),
  };

  /// Providers that are enabled AND fully configured.
  List<EcommerceProviderStatus> get readyProviders =>
      providers.where((p) => p.enabled && p.configured).toList();

  /// Providers that are enabled but missing required configuration.
  List<EcommerceProviderStatus> get incompleteProviders =>
      providers.where((p) => p.enabled && !p.configured).toList();
}
