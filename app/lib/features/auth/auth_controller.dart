import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/network/api_client.dart';
import 'auth_api.dart';
import 'auth_models.dart';

final authApiProvider = Provider<AuthApi>((ref) {
  final baseUrl = ref.watch(apiBaseUrlProvider);
  return AuthApi(baseUrl: baseUrl);
});

final authControllerProvider =
    ChangeNotifierProvider<AuthController>((ref) {
  return AuthController(ref.watch(authApiProvider));
});

/// Holds the in-memory auth session for the current Flutter process.
class AuthController extends ChangeNotifier {
  final AuthApi _api;
  AuthController(this._api);

  AuthSession? _session;
  CurrentUserInfo _currentUser = CurrentUserInfo.demo;
  String? _lastError;
  bool _loading = false;

  AuthSession? get session => _session;
  CurrentUserInfo get currentUser => _currentUser;
  String? get lastError => _lastError;
  bool get loading => _loading;
  bool get isAuthenticated => _session != null;

  Future<bool> register(String username, String password, {String? displayName}) async {
    return _withLoading(() async {
      _session = await _api.register(username, password, displayName);
      await _refreshMe();
    });
  }

  Future<bool> login(String username, String password) async {
    return _withLoading(() async {
      _session = await _api.login(username, password);
      await _refreshMe();
    });
  }

  Future<void> refresh() async {
    try {
      _currentUser = await _api.me(_session?.token);
      notifyListeners();
    } catch (_) {
      // keep prior state on transient failures
    }
  }

  void logout() {
    _session = null;
    _currentUser = CurrentUserInfo.demo;
    _lastError = null;
    notifyListeners();
  }

  Future<bool> _withLoading(Future<void> Function() action) async {
    _loading = true;
    _lastError = null;
    notifyListeners();
    try {
      await action();
      return true;
    } on AuthApiException catch (e) {
      _lastError = e.message;
      return false;
    } catch (e) {
      _lastError = '网络异常：$e';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> _refreshMe() async {
    try {
      _currentUser = await _api.me(_session?.token);
    } catch (_) {
      // tolerate
    }
  }
}
