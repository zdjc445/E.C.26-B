import 'package:app_core/app_core_domain.dart';
import '../../domain/entities/favorite_entity.dart';
import '../models/favorite_dto.dart';

/// Maps favorite DTOs to domain entities.
class FavoriteMapper {
  /// Convert a single [FavoriteDto] to a [FavoriteEntity].
  static FavoriteEntity fromDto(FavoriteDto dto) {
    return FavoriteEntity(
      favoriteId: dto.favoriteId,
      platformProductId: dto.platformProductId,
      platform: dto.platform,
      title: dto.title,
      price: Money.fromJson(dto.price),
      note: dto.note,
      createdAt: DateTime.parse(dto.createdAt),
    );
  }

  /// Convert a [FavoriteListDto] to the paginated tuple used by the domain.
  static ({
    List<FavoriteEntity> items,
    int page,
    int pageSize,
    int total,
  }) listFromDto(FavoriteListDto dto) {
    return (
      items: dto.items.map(fromDto).toList(),
      page: dto.page,
      pageSize: dto.pageSize,
      total: dto.total,
    );
  }
}
