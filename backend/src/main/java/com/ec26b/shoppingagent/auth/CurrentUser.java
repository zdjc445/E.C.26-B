package com.ec26b.shoppingagent.auth;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.Optional;

/**
 * Resolves the current authenticated user from the JWT Bearer token,
 * with optional fallback to a demo user when auth is disabled.
 */
@Component
public class CurrentUser {

    private static final long DEMO_USER_ID = 0L;
    private static final String DEMO_USERNAME = "demo";

    private final JwtService jwtService;
    private final boolean authEnabled;

    public CurrentUser(JwtService jwtService,
                       @Value("${app.auth.enabled:false}") boolean authEnabled) {
        this.jwtService = jwtService;
        this.authEnabled = authEnabled;
    }

    public Optional<JwtService.AuthenticatedUser> resolve(HttpServletRequest request) {
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {
            return jwtService.parse(header.substring(7).trim());
        }
        if (!authEnabled) {
            return Optional.of(new JwtService.AuthenticatedUser(DEMO_USER_ID, DEMO_USERNAME, "USER"));
        }
        return Optional.empty();
    }

    public JwtService.AuthenticatedUser require(HttpServletRequest request) {
        return resolve(request).orElseThrow(() ->
                new AuthService.AuthException(40101, "未登录或登录已过期"));
    }

    public boolean authEnabled() {
        return authEnabled;
    }

    public long demoUserId() {
        return DEMO_USER_ID;
    }
}
