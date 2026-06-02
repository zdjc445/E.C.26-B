import 'package:app_core/app_core.dart';
import '../entities/price_alert_entity.dart';
import '../repositories/price_alert_repository.dart';

class UpdateAlertParams {
  final String priceAlertId;
  final Money? targetPrice;
  final bool? enabled;

  const UpdateAlertParams({
    required this.priceAlertId,
    this.targetPrice,
    this.enabled,
  });
}

class UpdateAlert {
  final PriceAlertRepository _repo;

  const UpdateAlert(this._repo);

  Future<Either<Failure, PriceAlertEntity>> call(UpdateAlertParams params) async {
    if (params.priceAlertId.isEmpty) {
      return const Left(ValidationFailure({
        'priceAlertId': '价格提醒 ID 不能为空',
      }));
    }
    if (params.targetPrice != null && params.targetPrice!.amountAsDouble <= 0) {
      return const Left(ValidationFailure({
        'targetPrice': '目标价格必须大于 0',
      }));
    }
    if (params.targetPrice == null && params.enabled == null) {
      return const Left(ValidationFailure({
        'update': '至少需要修改目标价格或启用状态',
      }));
    }
    return _repo.updateAlert(
      params.priceAlertId,
      targetPrice: params.targetPrice,
      enabled: params.enabled,
    );
  }
}
