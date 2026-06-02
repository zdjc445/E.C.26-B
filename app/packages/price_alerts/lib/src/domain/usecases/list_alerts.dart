import 'package:app_core/app_core.dart';
import '../entities/price_alert_entity.dart';
import '../repositories/price_alert_repository.dart';

class ListAlertsParams {
  final int page;
  final int pageSize;

  const ListAlertsParams({this.page = 1, this.pageSize = 20})
    : assert(page >= 1),
      assert(pageSize >= 1 && pageSize <= 100);
}

class ListAlerts {
  final PriceAlertRepository _repo;

  const ListAlerts(this._repo);

  Future<Either<Failure, ({
    List<PriceAlertEntity> items,
    int page,
    int pageSize,
    int total,
  })>> call(ListAlertsParams params) async {
    return _repo.listAlerts(page: params.page, pageSize: params.pageSize);
  }
}
