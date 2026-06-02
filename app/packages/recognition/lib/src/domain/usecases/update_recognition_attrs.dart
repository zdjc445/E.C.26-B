import 'package:app_core/app_core.dart';
import '../entities/recognition_entity.dart';
import '../repositories/recognition_repository.dart';

/// Parameters for updating recognition attributes.
class UpdateRecognitionAttrsParams {
  final String recognitionId;
  final String? category;
  final String? brand;
  final String? model;
  final Map<String, dynamic>? attributes;

  const UpdateRecognitionAttrsParams({
    required this.recognitionId,
    this.category,
    this.brand,
    this.model,
    this.attributes,
  });
}

/// UseCase: Update/correct recognition attributes.
class UpdateRecognitionAttrs {
  final RecognitionRepository _repo;
  const UpdateRecognitionAttrs(this._repo);

  Future<Either<Failure, RecognitionEntity>> call(
    UpdateRecognitionAttrsParams params,
  ) {
    if (params.recognitionId.isEmpty) {
      return Future.value(
        const Left(ValidationFailure({'recognitionId': '识别结果ID不能为空'})),
      );
    }
    return _repo.updateAttributes(
      recognitionId: params.recognitionId,
      category: params.category,
      brand: params.brand,
      model: params.model,
      attributes: params.attributes,
    );
  }
}
