import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/ecommerce_status_entity.dart';
import '../../domain/entities/ecommerce_diagnostics_entity.dart';
import '../../domain/repositories/ecommerce_repository.dart';
import '../datasources/ecommerce_remote_datasource.dart';
import '../mappers/ecommerce_mapper.dart';

class EcommerceRepositoryImpl implements EcommerceRepository {
  final EcommerceRemoteDataSource _remote;

  EcommerceRepositoryImpl(this._remote);

  @override
  Future<Either<Failure, EcommerceStatusEntity>> getEcommerceStatus() async {
    try {
      final dto = await _remote.getStatus();
      return Right(EcommerceMapper.statusFromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, EcommerceDiagnosticsEntity>> runDiagnostics({
    String query = '',
    int pageSize = 3,
    String? platforms,
  }) async {
    try {
      final dto = await _remote.runDiagnostics(
        query: query,
        pageSize: pageSize,
        platforms: platforms,
      );
      return Right(EcommerceMapper.diagnosticsFromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }
}
