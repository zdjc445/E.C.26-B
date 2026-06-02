import '../../domain/entities/recognition_entity.dart';
import '../../domain/entities/suggestion_card.dart';
import '../models/recognition_dto.dart';

/// Maps RecognitionDto to domain RecognitionEntity and vice versa.
class RecognitionMapper {
  static RecognitionEntity fromDto(RecognitionDto dto) {
    return RecognitionEntity(
      recognitionId: dto.recognitionId,
      imageId: dto.imageId,
      category: dto.category,
      brand: dto.brand,
      model: dto.model,
      keywords: dto.keywords.map((e) => e.toString()).toList(),
      attributes: Map<String, dynamic>.from(dto.attributes),
      suggestionCards: dto.suggestionCards
          .map((e) => SuggestionCard.fromJson(e as Map<String, dynamic>))
          .toList(),
      confidence: dto.confidence,
      aiProvider: dto.aiProvider,
      fallbackUsed: dto.fallbackUsed,
      explanation: dto.explanation,
      notices: dto.notices.map((e) => e.toString()).toList(),
      status: dto.status,
      createdAt: DateTime.tryParse(dto.createdAt) ?? DateTime.now(),
    );
  }

  static RecognitionDto toDto(RecognitionEntity entity) {
    return RecognitionDto(
      recognitionId: entity.recognitionId,
      imageId: entity.imageId,
      category: entity.category,
      brand: entity.brand,
      model: entity.model,
      keywords: entity.keywords,
      attributes: entity.attributes,
      suggestionCards: entity.suggestionCards.map((c) => c.toJson()).toList(),
      confidence: entity.confidence,
      aiProvider: entity.aiProvider,
      fallbackUsed: entity.fallbackUsed,
      explanation: entity.explanation,
      notices: entity.notices,
      status: entity.status,
      createdAt: entity.createdAt.toIso8601String(),
    );
  }
}
