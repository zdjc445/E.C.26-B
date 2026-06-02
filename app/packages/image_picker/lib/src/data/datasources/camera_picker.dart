import 'package:app_core/app_core.dart';
import 'package:image_picker/image_picker.dart' as ip;

/// Wraps the platform image_picker package for camera and gallery access.
class CameraPicker {
  final ip.ImagePicker _picker;

  CameraPicker() : _picker = ip.ImagePicker();

  /// Open the device camera and return the captured file path.
  Future<Either<Failure, String>> pickFromCamera() async {
    try {
      final xfile = await _picker.pickImage(
        source: ip.ImageSource.camera,
        imageQuality: 85,
        maxWidth: 1920,
        maxHeight: 1920,
      );
      if (xfile == null) {
        return const Left(UnexpectedFailure('用户取消了拍照'));
      }
      return Right(xfile.path);
    } catch (e) {
      return Left(UnexpectedFailure('打开相机失败: ${e.toString()}'));
    }
  }

  /// Open the device gallery and return the selected file path.
  Future<Either<Failure, String>> pickFromGallery() async {
    try {
      final xfile = await _picker.pickImage(
        source: ip.ImageSource.gallery,
        imageQuality: 85,
        maxWidth: 1920,
        maxHeight: 1920,
      );
      if (xfile == null) {
        return const Left(UnexpectedFailure('用户取消了选择'));
      }
      return Right(xfile.path);
    } catch (e) {
      return Left(UnexpectedFailure('打开相册失败: ${e.toString()}'));
    }
  }
}
