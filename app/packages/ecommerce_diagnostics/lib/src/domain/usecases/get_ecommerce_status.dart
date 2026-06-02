import 'package:app_core/app_core.dart';
import '../entities/ecommerce_status_entity.dart';
import '../repositories/ecommerce_repository.dart';

class GetEcommerceStatus {
  final EcommerceRepository _repo;

  const GetEcommerceStatus(this._repo);

  Future<Either<Failure, EcommerceStatusEntity>> call() async {
    return _repo.getEcommerceStatus();
  }
}
