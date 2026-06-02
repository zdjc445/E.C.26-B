import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/image_entity.dart';
import '../../domain/repositories/image_repository.dart';
import '../datasources/camera_picker.dart';
import '../datasources/image_remote_datasource.dart';
import '../mappers/image_mapper.dart';

class ImageRepositoryImpl implements ImageRepository {
  final CameraPicker _picker;
  final ImageRemoteDataSource _remote;

  ImageRepositoryImpl(this._picker, this._remote);

  @override
  Future<Either<Failure, String>> pickFromCamera() async {
    return _picker.pickFromCamera();
  }

  @override
  Future<Either<Failure, String>> pickFromGallery() async {
    return _picker.pickFromGallery();
  }

  @override
  Future<Either<Failure, ImageEntity>> uploadImage(String filePath) async {
    try {
      final dto = await _remote.uploadImage(filePath);
      return Right(ImageMapper.fromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }
}
