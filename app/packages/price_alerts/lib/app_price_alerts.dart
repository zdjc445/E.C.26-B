/// app_price_alerts — Price alerts module barrel.
///
/// Exposes:
///   - GoRouter route configuration for /price-alerts
///   - PriceAlertProvider for state management
///   - Domain entities for other packages that may need them
library app_price_alerts;

// Entities
export 'src/domain/entities/price_alert_entity.dart' show PriceAlertEntity;

// Use cases
export 'src/domain/usecases/create_alert.dart' show CreateAlert, CreateAlertParams;
export 'src/domain/usecases/update_alert.dart' show UpdateAlert, UpdateAlertParams;
export 'src/domain/usecases/delete_alert.dart' show DeleteAlert;
export 'src/domain/usecases/list_alerts.dart' show ListAlerts, ListAlertsParams;

// Provider
export 'src/presentation/providers/price_alert_provider.dart'
    show priceAlertProvider, PriceAlertNotifier, PriceAlertsState, AlertsLoadStatus;

// Screen
export 'src/presentation/screens/price_alerts_screen.dart' show PriceAlertsScreen;

// Widgets
export 'src/presentation/widgets/price_alert_card.dart' show PriceAlertCard;

// Route builder
import 'package:go_router/go_router.dart';
import 'src/presentation/screens/price_alerts_screen.dart';

List<RouteBase> priceAlertsRoutes() => [
      GoRoute(
        path: '/price-alerts',
        builder: (context, state) => const PriceAlertsScreen(),
      ),
    ];
