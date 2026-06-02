import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/recognition_entity.dart';
import '../../domain/repositories/recognition_repository.dart';
import '../datasources/recognition_remote_datasource.dart';
import '../mappers/recognition_mapper.dart';

class RecognitionRepositoryImpl implements RecognitionRepository {
  final RecognitionRemoteDataSource _remote;

  RecognitionRepositoryImpl(this._remote);

  @override
  Future<Either<Failure, RecognitionEntity>> recognizeProduct(
    String imageId,
  ) async {
    try {
      final dto = await _remote.recognizeProduct(imageId);
      return Right(RecognitionMapper.fromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, RecognitionEntity>> updateAttributes({
    required String recognitionId,
    String? category,
    String? brand,
    String? model,
    Map<String, dynamic>? attributes,
  }) async {
    try {
      final dto = await _remote.updateAttributes(
        recognitionId: recognitionId,
        category: category,
        brand: brand,
        model: model,
        attributes: attributes,
      );
      return Right(RecognitionMapper.fromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }
}
