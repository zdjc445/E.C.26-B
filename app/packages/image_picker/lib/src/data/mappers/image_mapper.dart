import '../../domain/entities/image_entity.dart';
import '../models/image_dto.dart';

/// Maps ImageDto to domain ImageEntity.
class ImageMapper {
  static ImageEntity fromDto(ImageDto dto) {
    return ImageEntity(
      imageId: dto.imageId,
      imageUrl: dto.imageUrl,
      contentType: dto.contentType,
      size: dto.size,
      createdAt: DateTime.tryParse(dto.createdAt) ?? DateTime.now(),
    );
  }

  static ImageDto toDto(ImageEntity entity) {
    return ImageDto(
      imageId: entity.imageId,
      imageUrl: entity.imageUrl,
      contentType: entity.contentType,
      size: entity.size,
      createdAt: entity.createdAt.toIso8601String(),
    );
  }
}
