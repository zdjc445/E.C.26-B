/// app_ecommerce_diagnostics — E-commerce diagnostics module barrel.
///
/// Exposes:
///   - GoRouter route configuration for /ecommerce/diagnostics
///   - EcommerceProvider for state management
///   - Domain entities for other packages (diagnostics status/result types)
library app_ecommerce_diagnostics;

// Entities
export 'src/domain/entities/ecommerce_status_entity.dart'
    show EcommerceStatusEntity, EcommerceProviderStatus;
export 'src/domain/entities/ecommerce_diagnostics_entity.dart'
    show EcommerceDiagnosticsEntity, EcommerceProviderDiagnostic;

// Use cases
export 'src/domain/usecases/get_ecommerce_status.dart' show GetEcommerceStatus;
export 'src/domain/usecases/run_diagnostics.dart'
    show RunDiagnostics, RunDiagnosticsParams;

// Provider
export 'src/presentation/providers/ecommerce_provider.dart'
    show ecommerceProvider, EcommerceNotifier, EcommerceState, EcommerceLoadStatus;

// Screen
export 'src/presentation/screens/diagnostics_screen.dart' show DiagnosticsScreen;

// Widgets
export 'src/presentation/widgets/diagnostics_card.dart' show DiagnosticsCard;
export 'src/presentation/widgets/platform_status_pill.dart' show PlatformStatusPill;

// Route builder
import 'package:go_router/go_router.dart';
import 'src/presentation/screens/diagnostics_screen.dart';

List<RouteBase> diagnosticsRoutes() => [
      GoRoute(
        path: '/ecommerce/diagnostics',
        builder: (context, state) => const DiagnosticsScreen(),
      ),
    ];
