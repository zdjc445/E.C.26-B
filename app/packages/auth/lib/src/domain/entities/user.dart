/// Domain entity for a registered user.
class User {
  final int id;
  final String username;
  final String? nickname;
  final String? avatarUrl;
  final String status;

  const User({
    required this.id,
    required this.username,
    this.nickname,
    this.avatarUrl,
    this.status = 'active',
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as int,
      username: json['username'] as String,
      nickname: json['nickname'] as String?,
      avatarUrl: json['avatarUrl'] as String?,
      status: json['status'] as String? ?? 'active',
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'username': username,
    'nickname': nickname,
    'avatarUrl': avatarUrl,
    'status': status,
  };

  String get displayName => nickname ?? username;

  @override
  bool operator ==(Object other) =>
      identical(this, other) || other is User && id == other.id;
  @override
  int get hashCode => id.hashCode;
}

/// Pair of tokens returned by login / register / refresh.
class AuthCredentials {
  final String accessToken;
  final String refreshToken;
  final int expiresIn;
  final User user;

  const AuthCredentials({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
    required this.user,
  });

  factory AuthCredentials.fromJson(Map<String, dynamic> json) {
    return AuthCredentials(
      accessToken: json['accessToken'] as String,
      refreshToken: json['refreshToken'] as String,
      expiresIn: json['expiresIn'] as int? ?? 7200,
      user: User.fromJson(json['user'] as Map<String, dynamic>),
    );
  }
}
