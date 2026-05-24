package com.ec26b.shoppingagent.security;

import com.ec26b.shoppingagent.service.ShoppingService;
import com.ec26b.shoppingagent.api.ApiException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {
    private final JwtService jwtService;
    private final ShoppingService shoppingService;

    public JwtAuthenticationFilter(JwtService jwtService, ShoppingService shoppingService) {
        this.jwtService = jwtService;
        this.shoppingService = shoppingService;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        try {
            if (header != null && header.startsWith("Bearer ")) {
                long userId = jwtService.requireUserId(header.substring(7));
                shoppingService.requireUser(userId);
                SecurityContextHolder.getContext().setAuthentication(
                        new UsernamePasswordAuthenticationToken(userId, null, List.of())
                );
            }
        } catch (ApiException ex) {
            response.setStatus(ex.status().value());
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"code\":" + ex.code() + ",\"message\":\"" + ex.getMessage() + "\",\"data\":null}");
            return;
        }
        filterChain.doFilter(request, response);
    }
}
