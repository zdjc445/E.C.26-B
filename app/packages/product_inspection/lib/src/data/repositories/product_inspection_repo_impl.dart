import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/price_history_entity.dart';
import '../../domain/entities/review_summary_entity.dart';
import '../../domain/repositories/product_inspection_repository.dart';
import '../datasources/product_inspection_remote_data_source.dart';
import '../mappers/price_mapper.dart';

class ProductInspectionRepositoryImpl
    implements ProductInspectionRepository {
  final ProductInspectionRemoteDataSource _remote;

  ProductInspectionRepositoryImpl(this._remote);

  @override
  Future<Either<Failure, PriceHistoryEntity>> getPriceHistory({
    required String platformProductId,
    int days = 90,
  }) async {
    try {
      final dto = await _remote.getPriceHistory(
        platformProductId: platformProductId,
        days: days,
      );
      return Right(PriceMapper.priceHistoryFromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, ReviewSummaryEntity>> getReviewSummary({
    required String platformProductId,
  }) async {
    try {
      final dto = await _remote.getReviewSummary(
        platformProductId: platformProductId,
      );
      return Right(PriceMapper.reviewSummaryFromDto(dto));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }
}
