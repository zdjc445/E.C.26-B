import '../../domain/entities/ecommerce_status_entity.dart';
import '../../domain/entities/ecommerce_diagnostics_entity.dart';
import '../models/ecommerce_dto.dart';

/// Maps e-commerce DTOs to domain entities.
class EcommerceMapper {
  /// Convert an [EcommerceStatusDto] to an [EcommerceStatusEntity].
  static EcommerceStatusEntity statusFromDto(EcommerceStatusDto dto) {
    return EcommerceStatusEntity(
      enabled: dto.enabled,
      hasConfiguredClient: dto.hasConfiguredClient,
      providers: dto.providers
          .map((p) => EcommerceProviderStatus(
                platform: p.platform,
                enabled: p.enabled,
                configured: p.configured,
                requiredConfig: p.requiredConfig,
                missingConfig: p.missingConfig,
              ))
          .toList(),
    );
  }

  /// Convert an [EcommerceDiagnosticsDto] to an [EcommerceDiagnosticsEntity].
  static EcommerceDiagnosticsEntity diagnosticsFromDto(
      EcommerceDiagnosticsDto dto) {
    return EcommerceDiagnosticsEntity(
      query: dto.query,
      checkedAt: DateTime.parse(dto.checkedAt),
      providers: dto.providers
          .map((p) => EcommerceProviderDiagnostic(
                platform: p.platform,
                configured: p.configured,
                success: p.success,
                status: p.status,
                itemCount: p.itemCount,
                durationMs: p.durationMs,
                sampleTitles: p.sampleTitles,
                errorCode: p.errorCode,
                errorMessage: p.errorMessage,
                missingConfig: p.missingConfig,
              ))
          .toList(),
    );
  }
}
