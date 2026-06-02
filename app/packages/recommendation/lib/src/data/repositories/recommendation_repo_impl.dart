import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/recommendation_entity.dart';
import '../../domain/repositories/recommendation_repository.dart';
import '../datasources/recommendation_remote_data_source.dart';
import '../mappers/recommendation_mapper.dart';
import '../models/recommendation_dto.dart';

class RecommendationRepositoryImpl implements RecommendationRepository {
  final RecommendationRemoteDataSource _remote;

  RecommendationRepositoryImpl(this._remote);

  @override
  Future<Either<Failure, RecommendationEntity>> createRecommendation({
    required String searchTaskId,
    required String userQuery,
    required List<String> candidateIds,
  }) async {
    try {
      final dto = await _remote.createRecommendation(
        CreateRecommendationRequest(
          searchTaskId: searchTaskId,
          userQuery: userQuery,
          candidateIds: candidateIds,
        ),
      );
      return Right(RecommendationMapper.entityFromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }
}
