import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/favorite_entity.dart';
import '../../domain/repositories/favorite_repository.dart';
import '../datasources/favorite_remote_datasource.dart';
import '../mappers/favorite_mapper.dart';

class FavoriteRepositoryImpl implements FavoriteRepository {
  final FavoriteRemoteDataSource _remote;

  FavoriteRepositoryImpl(this._remote);

  @override
  Future<Either<Failure, FavoriteEntity>> addFavorite({
    required String platformProductId,
    String? note,
  }) async {
    try {
      final dto = await _remote.addFavorite(
        platformProductId: platformProductId,
        note: note,
      );
      return Right(FavoriteMapper.fromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, void>> removeFavorite(String favoriteId) async {
    try {
      await _remote.removeFavorite(favoriteId);
      return const Right(null);
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, ({
    List<FavoriteEntity> items,
    int page,
    int pageSize,
    int total,
  })>> listFavorites({int page = 1, int pageSize = 20}) async {
    try {
      final dto = await _remote.listFavorites(page: page, pageSize: pageSize);
      return Right(FavoriteMapper.listFromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }
}
