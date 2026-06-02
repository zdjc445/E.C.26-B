import 'package:app_core/app_core.dart';
import '../entities/image_entity.dart';

/// Contract for image capture, selection, and upload operations.
abstract class ImageRepository {
  /// Pick an image using the device camera. Returns the local file path.
  Future<Either<Failure, String>> pickFromCamera();

  /// Pick an image from the device gallery. Returns the local file path.
  Future<Either<Failure, String>> pickFromGallery();

  /// Upload an image file to the backend. Returns the persisted [ImageEntity].
  Future<Either<Failure, ImageEntity>> uploadImage(String filePath);
}
