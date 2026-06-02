import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/image_entity.dart';
import '../../domain/usecases/pick_from_camera.dart';
import '../../domain/usecases/pick_from_gallery.dart';
import '../../domain/usecases/upload_image.dart';
import '../../data/datasources/camera_picker.dart';
import '../../data/datasources/image_remote_datasource.dart';
import '../../data/repositories/image_repository_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _pickerProvider = Provider<CameraPicker>((ref) => CameraPicker());

final _imageRemoteProvider = Provider<ImageRemoteDataSource>(
  (ref) => ImageRemoteDataSource(ref.read(appDioProvider)),
);

final _imageRepoProvider = Provider<ImageRepositoryImpl>(
  (ref) => ImageRepositoryImpl(
    ref.read(_pickerProvider),
    ref.read(_imageRemoteProvider),
  ),
);

// ── Use cases ─────────────────────────────────────────────
final pickFromCameraUseCaseProvider = Provider<PickFromCamera>(
  (ref) => PickFromCamera(ref.read(_imageRepoProvider)),
);

final pickFromGalleryUseCaseProvider = Provider<PickFromGallery>(
  (ref) => PickFromGallery(ref.read(_imageRepoProvider)),
);

final uploadImageUseCaseProvider = Provider<UploadImage>(
  (ref) => UploadImage(ref.read(_imageRepoProvider)),
);

// ── Image state ──────────────────────────────────────────
enum ImagePickerStatus { idle, picking, picked, uploading, uploaded, error }

class ImagePickerState {
  final ImagePickerStatus status;
  final String? localPath;
  final ImageEntity? uploadedImage;
  final String? error;

  const ImagePickerState({
    this.status = ImagePickerStatus.idle,
    this.localPath,
    this.uploadedImage,
    this.error,
  });

  ImagePickerState copyWith({
    ImagePickerStatus? status,
    String? localPath,
    ImageEntity? uploadedImage,
    String? error,
  }) {
    return ImagePickerState(
      status: status ?? this.status,
      localPath: localPath ?? this.localPath,
      uploadedImage: uploadedImage ?? this.uploadedImage,
      error: error,
    );
  }
}

class ImagePickerNotifier extends StateNotifier<ImagePickerState> {
  final PickFromCamera _pickFromCamera;
  final PickFromGallery _pickFromGallery;
  final UploadImage _uploadImage;

  ImagePickerNotifier({
    required PickFromCamera pickFromCamera,
    required PickFromGallery pickFromGallery,
    required UploadImage uploadImage,
  })  : _pickFromCamera = pickFromCamera,
        _pickFromGallery = pickFromGallery,
        _uploadImage = uploadImage,
        super(const ImagePickerState());

  Future<void> pickFromCamera() async {
    state = state.copyWith(status: ImagePickerStatus.picking, error: null);
    final result = await _pickFromCamera();
    result.fold(
      (failure) => state = state.copyWith(
        status: ImagePickerStatus.error,
        error: _failureMessage(failure),
      ),
      (path) => state = state.copyWith(
        status: ImagePickerStatus.picked,
        localPath: path,
      ),
    );
  }

  Future<void> pickFromGallery() async {
    state = state.copyWith(status: ImagePickerStatus.picking, error: null);
    final result = await _pickFromGallery();
    result.fold(
      (failure) => state = state.copyWith(
        status: ImagePickerStatus.error,
        error: _failureMessage(failure),
      ),
      (path) => state = state.copyWith(
        status: ImagePickerStatus.picked,
        localPath: path,
      ),
    );
  }

  Future<void> uploadImage() async {
    final path = state.localPath;
    if (path == null) return;

    state = state.copyWith(status: ImagePickerStatus.uploading, error: null);
    final result = await _uploadImage(path);
    result.fold(
      (failure) => state = state.copyWith(
        status: ImagePickerStatus.error,
        error: _failureMessage(failure),
      ),
      (entity) => state = state.copyWith(
        status: ImagePickerStatus.uploaded,
        uploadedImage: entity,
      ),
    );
  }

  void reset() {
    state = const ImagePickerState();
  }

  String _failureMessage(Failure failure) {
    return switch (failure) {
      ServerFailure(:final message) => message,
      NetworkFailure(:final message) => message,
      ValidationFailure(:final errors) => errors.values.join('；'),
      UnexpectedFailure(:final message) => message,
      _ => '操作失败，请重试',
    };
  }
}

final imagePickerProvider =
    StateNotifierProvider<ImagePickerNotifier, ImagePickerState>((ref) {
  return ImagePickerNotifier(
    pickFromCamera: ref.read(pickFromCameraUseCaseProvider),
    pickFromGallery: ref.read(pickFromGalleryUseCaseProvider),
    uploadImage: ref.read(uploadImageUseCaseProvider),
  );
});
