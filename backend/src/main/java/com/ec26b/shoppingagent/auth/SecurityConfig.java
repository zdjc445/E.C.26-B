package com.ec26b.shoppingagent.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Open security configuration — authentication is enforced inside controllers via
 * {@link CurrentUser} rather than the filter chain. This keeps the AI demo path
 * accessible while still allowing the JWT flow for protected operations such as
 * favorites and price alerts.
 */
@Configuration
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .cors(cors -> {})
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .formLogin(form -> form.disable())
                .httpBasic(basic -> basic.disable())
                .authorizeHttpRequests(a -> a.anyRequest().permitAll());
        return http.build();
    }
}
