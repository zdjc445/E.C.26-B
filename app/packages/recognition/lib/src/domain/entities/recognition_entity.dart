import 'suggestion_card.dart';

/// Domain entity for a product recognition result.
class RecognitionEntity {
  final String recognitionId;
  final String imageId;
  final String? category;
  final String? brand;
  final String? model;
  final List<String> keywords;
  final Map<String, dynamic> attributes;
  final List<SuggestionCard> suggestionCards;
  final double confidence;
  final String aiProvider;
  final bool fallbackUsed;
  final String? explanation;
  final List<String> notices;
  final String status;
  final DateTime createdAt;

  const RecognitionEntity({
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

  factory RecognitionEntity.fromJson(Map<String, dynamic> json) {
    final suggestionCardsRaw = json['suggestionCards'] as List<dynamic>?;
    final keywordsRaw = json['keywords'] as List<dynamic>?;
    final noticesRaw = json['notices'] as List<dynamic>?;

    return RecognitionEntity(
      recognitionId: json['recognitionId'] as String,
      imageId: json['imageId'] as String,
      category: json['category'] as String?,
      brand: json['brand'] as String?,
      model: json['model'] as String?,
      keywords: keywordsRaw?.map((e) => e.toString()).toList() ?? [],
      attributes: Map<String, dynamic>.from(
        json['attributes'] as Map<String, dynamic>? ?? {},
      ),
      suggestionCards: suggestionCardsRaw
              ?.map((e) => SuggestionCard.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      aiProvider: json['aiProvider'] as String? ?? 'unknown',
      fallbackUsed: json['fallbackUsed'] as bool? ?? false,
      explanation: json['explanation'] as String?,
      notices: noticesRaw?.map((e) => e.toString()).toList() ?? [],
      status: json['status'] as String? ?? 'completed',
      createdAt: DateTime.tryParse(json['createdAt'] as String? ?? '') ??
          DateTime.now(),
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
    'suggestionCards': suggestionCards.map((c) => c.toJson()).toList(),
    'confidence': confidence,
    'aiProvider': aiProvider,
    'fallbackUsed': fallbackUsed,
    if (explanation != null) 'explanation': explanation,
    'notices': notices,
    'status': status,
    'createdAt': createdAt.toIso8601String(),
  };

  RecognitionEntity copyWith({
    String? category,
    String? brand,
    String? model,
    Map<String, dynamic>? attributes,
  }) {
    return RecognitionEntity(
      recognitionId: recognitionId,
      imageId: imageId,
      category: category ?? this.category,
      brand: brand ?? this.brand,
      model: model ?? this.model,
      keywords: keywords,
      attributes: attributes ?? this.attributes,
      suggestionCards: suggestionCards,
      confidence: confidence,
      aiProvider: aiProvider,
      fallbackUsed: fallbackUsed,
      explanation: explanation,
      notices: notices,
      status: status,
      createdAt: createdAt,
    );
  }

  /// A user-displayable label for the product name.
  String get displayName {
    if (brand != null && model != null) return '$brand $model';
    if (brand != null) return brand!;
    if (model != null) return model!;
    if (keywords.isNotEmpty) return keywords.first;
    return category ?? '未知商品';
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RecognitionEntity && recognitionId == other.recognitionId;

  @override
  int get hashCode => recognitionId.hashCode;
}
