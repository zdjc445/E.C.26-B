import 'package:app_core/app_core.dart';
import '../entities/recognition_entity.dart';

/// Contract for recognition data access.
abstract class RecognitionRepository {
  /// Submit an image for AI recognition. Returns the recognition result.
  Future<Either<Failure, RecognitionEntity>> recognizeProduct(String imageId);

  /// Update recognition attributes (category, brand, model, custom attributes).
  Future<Either<Failure, RecognitionEntity>> updateAttributes({
    required String recognitionId,
    String? category,
    String? brand,
    String? model,
    Map<String, dynamic>? attributes,
  });
}
