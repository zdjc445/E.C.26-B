import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/comparison_entity.dart';
import '../../domain/repositories/comparison_repository.dart';
import '../datasources/comparison_remote_data_source.dart';
import '../mappers/comparison_mapper.dart';
import '../models/comparison_dto.dart';

class ComparisonRepositoryImpl implements ComparisonRepository {
  final ComparisonRemoteDataSource _remote;

  ComparisonRepositoryImpl(this._remote);

  @override
  Future<Either<Failure, ComparisonEntity>> createComparison({
    required String searchTaskId,
    required List<String> platformProductIds,
  }) async {
    try {
      final dto = await _remote.createComparison(
        CreateComparisonRequest(
          searchTaskId: searchTaskId,
          platformProductIds: platformProductIds,
        ),
      );
      return Right(ComparisonMapper.entityFromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }
}
