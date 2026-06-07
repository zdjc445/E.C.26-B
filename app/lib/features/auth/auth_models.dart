class AuthSession {
  final String token;
  final int userId;
  final String username;
  final String displayName;
  final String role;
  final int expiresInSeconds;

  const AuthSession({
    required this.token,
    required this.userId,
    required this.username,
    required this.displayName,
    required this.role,
    required this.expiresInSeconds,
  });

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      token: json['token'] as String,
      userId: (json['userId'] as num).toInt(),
      username: json['username'] as String? ?? '',
      displayName: json['displayName'] as String? ?? '',
      role: json['role'] as String? ?? 'USER',
      expiresInSeconds: (json['expiresInSeconds'] as num?)?.toInt() ?? 0,
    );
  }
}

class CurrentUserInfo {
  final int userId;
  final String username;
  final String displayName;
  final bool authEnabled;

  const CurrentUserInfo({
    required this.userId,
    required this.username,
    required this.displayName,
    required this.authEnabled,
  });

  factory CurrentUserInfo.fromJson(Map<String, dynamic> json) {
    return CurrentUserInfo(
      userId: (json['userId'] as num?)?.toInt() ?? 0,
      username: json['username'] as String? ?? 'demo',
      displayName: json['displayName'] as String? ?? '演示用户',
      authEnabled: json['authEnabled'] as bool? ?? false,
    );
  }

  static const CurrentUserInfo demo = CurrentUserInfo(
    userId: 0,
    username: 'demo',
    displayName: '演示用户',
    authEnabled: false,
  );
}
