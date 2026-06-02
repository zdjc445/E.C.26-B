/// app_product_inspection — Product inspection module barrel.
///
/// Exposes:
///   - GoRouter route builders for /inspection/*
///   - ProductInspectionProvider for state management
///   - Domain entities for other packages
library app_product_inspection;

// Domain entities
export 'src/domain/entities/price_history_entity.dart';
export 'src/domain/entities/review_summary_entity.dart';

// Use cases
export 'src/domain/usecases/get_price_history.dart';
export 'src/domain/usecases/get_review_summary.dart';

// Providers
export 'src/presentation/providers/product_inspection_provider.dart'
    show productInspectionProvider, ProductInspectionState, ProductInspectionNotifier;

// Screens
export 'src/presentation/screens/price_history_screen.dart';

// GoRouter helper — returns the route configuration for this package.
import 'package:go_router/go_router.dart';
import 'src/presentation/screens/price_history_screen.dart';

List<RouteBase> inspectionRoutes() => [
  GoRoute(
    path: '/inspection/:platformProductId',
    builder: (context, state) {
      final platformProductId = state.pathParameters['platformProductId'] ?? '';
      return PriceHistoryScreen(
        platformProductId: platformProductId,
      );
    },
  ),
];
