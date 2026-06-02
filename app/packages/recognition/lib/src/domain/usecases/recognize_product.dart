import 'package:app_core/app_core.dart';
import '../entities/recognition_entity.dart';
import '../repositories/recognition_repository.dart';

/// UseCase: Submit an imageId for AI product recognition.
class RecognizeProduct {
  final RecognitionRepository _repo;
  const RecognizeProduct(this._repo);

  Future<Either<Failure, RecognitionEntity>> call(String imageId) {
    if (imageId.isEmpty) {
      return Future.value(
        const Left(ValidationFailure({'imageId': '图片ID不能为空'})),
      );
    }
    return _repo.recognizeProduct(imageId);
  }
}
