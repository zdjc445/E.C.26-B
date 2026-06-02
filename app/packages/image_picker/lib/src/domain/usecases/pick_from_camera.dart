import 'package:app_core/app_core.dart';
import '../repositories/image_repository.dart';

/// UseCase: Launch device camera to capture an image.
/// Returns the local file path of the captured image.
class PickFromCamera {
  final ImageRepository _repo;
  const PickFromCamera(this._repo);

  Future<Either<Failure, String>> call() => _repo.pickFromCamera();
}
