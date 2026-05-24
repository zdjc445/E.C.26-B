package com.ec26b.shoppingagent.ecommerce;

import com.ec26b.shoppingagent.api.ApiException;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.stream.Collectors;

final class EcommerceHttp {
    private EcommerceHttp() {
    }

    static String postForm(HttpClient httpClient, String url, Map<String, String> params, Duration timeout) {
        String body = params.entrySet().stream()
                .map(entry -> encode(entry.getKey()) + "=" + encode(entry.getValue()))
                .collect(Collectors.joining("&"));
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(timeout)
                .header("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                .build();
        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw ApiException.badRequest("official ecommerce api returned http " + response.statusCode());
            }
            return response.body();
        } catch (IOException ex) {
            throw ApiException.badRequest("official ecommerce api request failed: " + ex.getMessage());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw ApiException.badRequest("official ecommerce api request interrupted");
        }
    }

    private static String encode(String value) {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8);
    }
}
