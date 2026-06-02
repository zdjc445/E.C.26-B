import 'package:app_core/app_core.dart';
import '../repositories/price_alert_repository.dart';

class DeleteAlert {
  final PriceAlertRepository _repo;

  const DeleteAlert(this._repo);

  Future<Either<Failure, void>> call(String priceAlertId) async {
    if (priceAlertId.isEmpty) {
      return const Left(ValidationFailure({
        'priceAlertId': '价格提醒 ID 不能为空',
      }));
    }
    return _repo.deleteAlert(priceAlertId);
  }
}
