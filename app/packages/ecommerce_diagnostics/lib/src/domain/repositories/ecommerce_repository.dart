import 'package:app_core/app_core.dart';
import '../entities/ecommerce_status_entity.dart';
import '../entities/ecommerce_diagnostics_entity.dart';

/// Contract for e-commerce status and diagnostics data access.
/// Implemented in the data layer via remote Dio calls.
abstract class EcommerceRepository {
  /// Fetch the overall e-commerce configuration status (no auth).
  Future<Either<Failure, EcommerceStatusEntity>> getEcommerceStatus();

  /// Run diagnostics probes against configured e-commerce providers.
  Future<Either<Failure, EcommerceDiagnosticsEntity>> runDiagnostics({
    String query = '',
    int pageSize = 3,
    String? platforms,
  });
}
