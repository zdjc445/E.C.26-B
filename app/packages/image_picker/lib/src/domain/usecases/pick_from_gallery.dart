import 'package:app_core/app_core.dart';
import '../repositories/image_repository.dart';

/// UseCase: Launch device gallery to select an image.
/// Returns the local file path of the selected image.
class PickFromGallery {
  final ImageRepository _repo;
  const PickFromGallery(this._repo);

  Future<Either<Failure, String>> call() => _repo.pickFromGallery();
}
