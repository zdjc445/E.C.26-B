/// Domain entity representing an uploaded image.
class ImageEntity {
  final String imageId;
  final String imageUrl;
  final String contentType;
  final int size;
  final DateTime createdAt;

  const ImageEntity({
    required this.imageId,
    required this.imageUrl,
    required this.contentType,
    required this.size,
    required this.createdAt,
  });

  factory ImageEntity.fromJson(Map<String, dynamic> json) {
    return ImageEntity(
      imageId: json['imageId'] as String,
      imageUrl: json['imageUrl'] as String,
      contentType: json['contentType'] as String? ?? 'image/jpeg',
      size: json['size'] as int? ?? 0,
      createdAt: DateTime.tryParse(json['createdAt'] as String? ?? '') ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
    'imageId': imageId,
    'imageUrl': imageUrl,
    'contentType': contentType,
    'size': size,
    'createdAt': createdAt.toIso8601String(),
  };

  @override
  bool operator ==(Object other) =>
      identical(this, other) || other is ImageEntity && imageId == other.imageId;

  @override
  int get hashCode => imageId.hashCode;

  @override
  String toString() => 'ImageEntity(imageId: $imageId, imageUrl: $imageUrl)';
}
