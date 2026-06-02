import 'package:app_core/app_core.dart';
import '../entities/price_alert_entity.dart';
import '../repositories/price_alert_repository.dart';

class CreateAlertParams {
  final String platformProductId;
  final Money targetPrice;
  final bool enabled;

  const CreateAlertParams({
    required this.platformProductId,
    required this.targetPrice,
    this.enabled = true,
  });
}

class CreateAlert {
  final PriceAlertRepository _repo;

  const CreateAlert(this._repo);

  Future<Either<Failure, PriceAlertEntity>> call(CreateAlertParams params) async {
    if (params.platformProductId.isEmpty) {
      return const Left(ValidationFailure({
        'platformProductId': '商品 ID 不能为空',
      }));
    }
    if (params.targetPrice.amountAsDouble <= 0) {
      return const Left(ValidationFailure({
        'targetPrice': '目标价格必须大于 0',
      }));
    }
    return _repo.createAlert(
      platformProductId: params.platformProductId,
      targetPrice: params.targetPrice,
      enabled: params.enabled,
    );
  }
}
