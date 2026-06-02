/// Raw DTO mirroring the backend JSON for POST /api/recognitions and
/// PATCH /api/recognitions/{id}/attributes responses.
class RecognitionDto {
  final String recognitionId;
  final String imageId;
  final String? category;
  final String? brand;
  final String? model;
  final List<dynamic> keywords;
  final Map<String, dynamic> attributes;
  final List<dynamic> suggestionCards;
  final double confidence;
  final String aiProvider;
  final bool fallbackUsed;
  final String? explanation;
  final List<dynamic> notices;
  final String status;
  final String createdAt;

  const RecognitionDto({
    required this.recognitionId,
    required this.imageId,
    this.category,
    this.brand,
    this.model,
    this.keywords = const [],
    this.attributes = const {},
    this.suggestionCards = const [],
    required this.confidence,
    required this.aiProvider,
    this.fallbackUsed = false,
    this.explanation,
    this.notices = const [],
    this.status = 'completed',
    required this.createdAt,
  });

  factory RecognitionDto.fromJson(Map<String, dynamic> json) {
    return RecognitionDto(
      recognitionId: json['recognitionId'] as String,
      imageId: json['imageId'] as String,
      category: json['category'] as String?,
      brand: json['brand'] as String?,
      model: json['model'] as String?,
      keywords: List<dynamic>.from(json['keywords'] as List? ?? []),
      attributes: Map<String, dynamic>.from(json['attributes'] as Map? ?? {}),
      suggestionCards: List<dynamic>.from(json['suggestionCards'] as List? ?? []),
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      aiProvider: json['aiProvider'] as String? ?? 'unknown',
      fallbackUsed: json['fallbackUsed'] as bool? ?? false,
      explanation: json['explanation'] as String?,
      notices: List<dynamic>.from(json['notices'] as List? ?? []),
      status: json['status'] as String? ?? 'completed',
      createdAt: json['createdAt'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
    'recognitionId': recognitionId,
    'imageId': imageId,
    if (category != null) 'category': category,
    if (brand != null) 'brand': brand,
    if (model != null) 'model': model,
    'keywords': keywords,
    'attributes': attributes,
    'suggestionCards': suggestionCards,
    'confidence': confidence,
    'aiProvider': aiProvider,
    'fallbackUsed': fallbackUsed,
    if (explanation != null) 'explanation': explanation,
    'notices': notices,
    'status': status,
    'createdAt': createdAt,
  };
}
