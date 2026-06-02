import '../../domain/entities/user.dart';
import '../models/auth_dto.dart';

/// Maps auth DTOs ↔ domain entities.
class AuthMapper {
  static User userFromJson(Map<String, dynamic> json) => User.fromJson(json);

  static AuthCredentials credentialsFromDto(AuthResponseDto dto) {
    return AuthCredentials(
      accessToken: dto.accessToken,
      refreshToken: dto.refreshToken,
      expiresIn: dto.expiresIn,
      user: User.fromJson(dto.user),
    );
  }

  static AuthCredentials credentialsFromRefreshDto(
    RefreshResponseDto dto,
    User user,
  ) {
    return AuthCredentials(
      accessToken: dto.accessToken,
      refreshToken: dto.refreshToken,
      expiresIn: dto.expiresIn,
      user: user,
    );
  }
}
