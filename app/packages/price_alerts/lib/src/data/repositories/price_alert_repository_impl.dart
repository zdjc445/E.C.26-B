import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/price_alert_entity.dart';
import '../../domain/repositories/price_alert_repository.dart';
import '../datasources/price_alert_remote_datasource.dart';
import '../mappers/price_alert_mapper.dart';

class PriceAlertRepositoryImpl implements PriceAlertRepository {
  final PriceAlertRemoteDataSource _remote;

  PriceAlertRepositoryImpl(this._remote);

  @override
  Future<Either<Failure, PriceAlertEntity>> createAlert({
    required String platformProductId,
    required Money targetPrice,
    bool enabled = true,
  }) async {
    try {
      final dto = await _remote.createAlert(
        platformProductId: platformProductId,
        targetPrice: targetPrice.toJson(),
        enabled: enabled,
      );
      return Right(PriceAlertMapper.fromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, PriceAlertEntity>> updateAlert(
    String priceAlertId, {
    Money? targetPrice,
    bool? enabled,
  }) async {
    try {
      final dto = await _remote.updateAlert(
        priceAlertId,
        targetPrice: targetPrice?.toJson(),
        enabled: enabled,
      );
      return Right(PriceAlertMapper.fromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, void>> deleteAlert(String priceAlertId) async {
    try {
      await _remote.deleteAlert(priceAlertId);
      return const Right(null);
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, ({
    List<PriceAlertEntity> items,
    int page,
    int pageSize,
    int total,
  })>> listAlerts({int page = 1, int pageSize = 20}) async {
    try {
      final dto = await _remote.listAlerts(page: page, pageSize: pageSize);
      return Right(PriceAlertMapper.listFromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }
}
