import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../features/alerts/price_alerts_screen.dart';
import '../features/auth/login_screen.dart';
import '../features/chat/chat_screen.dart';
import '../features/favorites/favorites_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/memory/preferences_screen.dart';

/// Central router.
final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/home',
        builder: (context, state) => const ChatScreen(),
      ),
      GoRoute(
        path: '/me',
        builder: (context, state) => const ProfileScreen(),
      ),
      GoRoute(
        path: '/favorites',
        builder: (context, state) => const FavoritesScreen(),
      ),
      GoRoute(
        path: '/price-alerts',
        builder: (context, state) => const PriceAlertsScreen(),
      ),
      GoRoute(
        path: '/preferences',
        builder: (context, state) => const PreferencesScreen(),
      ),
    ],
  );
});
