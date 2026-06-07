package com.ec26b.shoppingagent.auth;

import org.springframework.stereotype.Service;

@Service
public class AuthService {

    private final UserRepository repository;
    private final PasswordHasher hasher;
    private final JwtService jwtService;

    public AuthService(UserRepository repository, PasswordHasher hasher, JwtService jwtService) {
        this.repository = repository;
        this.hasher = hasher;
        this.jwtService = jwtService;
    }

    public AuthResult register(String username, String password, String displayName) {
        validateUsernameAndPassword(username, password);
        if (repository.existsByUsername(username)) {
            throw new AuthException(40901, "用户名已被占用");
        }
        var user = repository.save(username, hasher.hash(password),
                displayName == null || displayName.isBlank() ? username : displayName);
        return toResult(user);
    }

    public AuthResult login(String username, String password) {
        if (username == null || username.isBlank() || password == null || password.isBlank()) {
            throw new AuthException(40001, "用户名或密码不能为空");
        }
        var maybeUser = repository.findByUsername(username);
        if (maybeUser.isEmpty() || !hasher.matches(password, maybeUser.get().passwordHash())) {
            throw new AuthException(40101, "用户名或密码错误");
        }
        return toResult(maybeUser.get());
    }

    public User requireUserById(long userId) {
        return repository.findById(userId)
                .orElseThrow(() -> new AuthException(40101, "用户不存在"));
    }

    private AuthResult toResult(User user) {
        String token = jwtService.issue(user);
        return new AuthResult(token, user.id(), user.username(), user.displayName(), user.role(),
                jwtService.ttlMinutes() * 60);
    }

    private void validateUsernameAndPassword(String username, String password) {
        if (username == null || username.isBlank()) {
            throw new AuthException(40001, "用户名不能为空");
        }
        if (username.length() < 3 || username.length() > 32) {
            throw new AuthException(40001, "用户名长度需在 3 - 32 之间");
        }
        if (password == null || password.length() < 6 || password.length() > 64) {
            throw new AuthException(40001, "密码长度需在 6 - 64 之间");
        }
    }

    public record AuthResult(String token, long userId, String username, String displayName,
                              String role, long expiresInSeconds) {}

    public static class AuthException extends RuntimeException {
        private final int code;

        public AuthException(int code, String message) {
            super(message);
            this.code = code;
        }

        public int code() {
            return code;
        }
    }
}
