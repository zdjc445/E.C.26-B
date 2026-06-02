/// Raw DTO mirroring the backend JSON response for POST /api/images.
class ImageDto {
  final String imageId;
  final String imageUrl;
  final String contentType;
  final int size;
  final String createdAt;

  const ImageDto({
    required this.imageId,
    required this.imageUrl,
    required this.contentType,
    required this.size,
    required this.createdAt,
  });

  factory ImageDto.fromJson(Map<String, dynamic> json) {
    return ImageDto(
      imageId: json['imageId'] as String,
      imageUrl: json['imageUrl'] as String,
      contentType: json['contentType'] as String? ?? 'image/jpeg',
      size: json['size'] as int? ?? 0,
      createdAt: json['createdAt'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
    'imageId': imageId,
    'imageUrl': imageUrl,
    'contentType': contentType,
    'size': size,
    'createdAt': createdAt,
  };
}
