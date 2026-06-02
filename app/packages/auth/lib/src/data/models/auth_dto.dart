/// Raw DTO mirroring the backend JSON for auth responses.
class AuthResponseDto {
  final String accessToken;
  final String refreshToken;
  final int expiresIn;
  final Map<String, dynamic> user;

  const AuthResponseDto({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
    required this.user,
  });

  factory AuthResponseDto.fromJson(Map<String, dynamic> json) {
    return AuthResponseDto(
      accessToken: json['accessToken'] as String,
      refreshToken: json['refreshToken'] as String,
      expiresIn: json['expiresIn'] as int? ?? 7200,
      user: json['user'] as Map<String, dynamic>,
    );
  }
}

class RefreshResponseDto {
  final String accessToken;
  final String refreshToken;
  final int expiresIn;

  const RefreshResponseDto({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
  });

  factory RefreshResponseDto.fromJson(Map<String, dynamic> json) {
    return RefreshResponseDto(
      accessToken: json['accessToken'] as String,
      refreshToken: json['refreshToken'] as String,
      expiresIn: json['expiresIn'] as int? ?? 7200,
    );
  }
}
