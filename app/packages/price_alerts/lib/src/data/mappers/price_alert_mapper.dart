import 'package:app_core/app_core_domain.dart';
import '../../domain/entities/price_alert_entity.dart';
import '../models/price_alert_dto.dart';

/// Maps price alert DTOs to domain entities.
class PriceAlertMapper {
  /// Convert a single [PriceAlertDto] to a [PriceAlertEntity].
  static PriceAlertEntity fromDto(PriceAlertDto dto) {
    return PriceAlertEntity(
      priceAlertId: dto.priceAlertId,
      platformProductId: dto.platformProductId,
      title: dto.title,
      currentPrice: Money.fromJson(dto.currentPrice),
      targetPrice: Money.fromJson(dto.targetPrice),
      enabled: dto.enabled,
      createdAt: DateTime.parse(dto.createdAt),
      updatedAt: DateTime.parse(dto.updatedAt),
    );
  }

  /// Convert a [PriceAlertListDto] to the paginated tuple used by the domain.
  static ({
    List<PriceAlertEntity> items,
    int page,
    int pageSize,
    int total,
  }) listFromDto(PriceAlertListDto dto) {
    return (
      items: dto.items.map(fromDto).toList(),
      page: dto.page,
      pageSize: dto.pageSize,
      total: dto.total,
    );
  }
}
