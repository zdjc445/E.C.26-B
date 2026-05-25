package com.ec26b.shoppingagent.ecommerce;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.regex.Pattern;

final class EcommerceHttp {
    private static final Set<String> SENSITIVE_PARAM_NAMES = Set.of(
            "client_id",
            "client_secret",
            "app_key",
            "app_secret",
            "access_token",
            "sign"
    );

    private EcommerceHttp() {
    }

    static String postForm(HttpClient httpClient, String url, Map<String, String> params, Duration timeout) {
        String body = params.entrySet().stream()
                .map(entry -> encode(entry.getKey()) + "=" + encode(entry.getValue()))
                .collect(Collectors.joining("&"));
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(timeout)
                    .header("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new OfficialApiException(
                        "http_" + response.statusCode(),
                        "official ecommerce api returned http " + response.statusCode() + responseBodyHint(response.body(), params)
                );
            }
            return response.body();
        } catch (HttpTimeoutException ex) {
            throw new OfficialApiException("timeout", "official ecommerce api request timed out");
        } catch (IOException ex) {
            throw new OfficialApiException("network_error", "official ecommerce api request failed: " + safeMessage(ex.getMessage()));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new OfficialApiException("interrupted", "official ecommerce api request interrupted");
        } catch (IllegalArgumentException ex) {
            throw new OfficialApiException("invalid_url", "official ecommerce api url is invalid");
        }
    }

    private static String encode(String value) {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8);
    }

    private static String responseBodyHint(String body, Map<String, String> params) {
        if (body == null || body.isBlank()) {
            return "";
        }
        String normalized = redact(body.replaceAll("\\s+", " ").trim(), params);
        if (normalized.length() > 180) {
            normalized = normalized.substring(0, 180);
        }
        return ": " + normalized;
    }

    private static String redact(String value, Map<String, String> params) {
        String redacted = value;
        for (Map.Entry<String, String> entry : params.entrySet()) {
            if (SENSITIVE_PARAM_NAMES.contains(entry.getKey()) && entry.getValue() != null && !entry.getValue().isBlank()) {
                redacted = redacted.replace(entry.getValue(), "[redacted]");
            }
        }
        for (String name : SENSITIVE_PARAM_NAMES) {
            redacted = redacted.replaceAll("(?i)(\"" + Pattern.quote(name) + "\"\\s*:\\s*\")[^\"]*(\")", "$1[redacted]$2");
            redacted = redacted.replaceAll("(?i)(" + Pattern.quote(name) + "=)[^&\\s]+", "$1[redacted]");
        }
        return redacted;
    }

    private static String safeMessage(String message) {
        if (message == null || message.isBlank()) {
            return "network error";
        }
        return message;
    }
}
