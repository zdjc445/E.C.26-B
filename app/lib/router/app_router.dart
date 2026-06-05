import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../features/auth/login_placeholder.dart';
import '../features/camera/camera_placeholder.dart';
import '../features/recognition/recognition_placeholder.dart';
import '../features/search/search_placeholder.dart';
import '../features/comparison/comparison_placeholder.dart';
import '../features/recommendation/recommendation_placeholder.dart';
import 'home_screen.dart';

/// Central router for the app skeleton.
///
/// All feature pages are placeholder stubs in this phase.
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
        builder: (context, state) => const HomeScreen(),
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
    ],
  );
});
