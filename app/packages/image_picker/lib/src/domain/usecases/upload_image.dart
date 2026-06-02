import 'package:app_core/app_core.dart';
import '../entities/image_entity.dart';
import '../repositories/image_repository.dart';

/// UseCase: Upload a local image file to the backend.
class UploadImage {
  final ImageRepository _repo;
  const UploadImage(this._repo);

  Future<Either<Failure, ImageEntity>> call(String filePath) {
    if (filePath.isEmpty) {
      return Future.value(
        const Left(ValidationFailure({'file': '请先选择或拍摄一张图片'})),
      );
    }
    return _repo.uploadImage(filePath);
  }
}
