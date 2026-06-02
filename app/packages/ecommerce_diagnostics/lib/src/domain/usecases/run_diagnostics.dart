import 'package:app_core/app_core.dart';
import '../entities/ecommerce_diagnostics_entity.dart';
import '../repositories/ecommerce_repository.dart';

class RunDiagnosticsParams {
  final String query;
  final int pageSize;
  final String? platforms;

  const RunDiagnosticsParams({
    this.query = '',
    this.pageSize = 3,
    this.platforms,
  }) : assert(pageSize >= 1 && pageSize <= 20);
}

class RunDiagnostics {
  final EcommerceRepository _repo;

  const RunDiagnostics(this._repo);

  Future<Either<Failure, EcommerceDiagnosticsEntity>> call(
      RunDiagnosticsParams params) async {
    return _repo.runDiagnostics(
      query: params.query,
      pageSize: params.pageSize,
      platforms: params.platforms,
    );
  }
}
