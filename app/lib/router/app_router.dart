import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../features/alerts/price_alerts_screen.dart';
import '../features/auth/login_placeholder.dart';
import '../features/camera/camera_placeholder.dart';
import '../features/chat/chat_screen.dart';
import '../features/comparison/comparison_placeholder.dart';
import '../features/favorites/favorites_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/memory/preferences_screen.dart';
import '../features/recognition/recognition_placeholder.dart';
import '../features/recommendation/recommendation_placeholder.dart';
import '../features/search/search_placeholder.dart';

/// Central router.
final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginPlaceholder(),
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
        path: '/camera',
        builder: (context, state) => const CameraPlaceholder(),
      ),
      GoRoute(
        path: '/recognition',
        builder: (context, state) => const RecognitionPlaceholder(),
      ),
      GoRoute(
        path: '/search',
        builder: (context, state) => const SearchPlaceholder(),
      ),
      GoRoute(
        path: '/comparison',
        builder: (context, state) => const ComparisonPlaceholder(),
      ),
      GoRoute(
        path: '/recommendation',
        builder: (context, state) => const RecommendationPlaceholder(),
      ),
      GoRoute(
        path: '/preferences',
        builder: (context, state) => const PreferencesScreen(),
      ),
    ],
  );
});
