package com.ec26b.shoppingagent.api;

import org.springframework.http.HttpStatus;

public class ApiException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final int code;
    private final HttpStatus status;

    public ApiException(int code, String message, HttpStatus status) {
        super(message);
        this.code = code;
        this.status = status;
    }

    public int code() {
        return code;
    }

    public HttpStatus status() {
        return status;
    }

    public static ApiException badRequest(String message) {
        return new ApiException(40000, message, HttpStatus.BAD_REQUEST);
    }

    public static ApiException unauthorized(String message) {
        return new ApiException(40101, message, HttpStatus.UNAUTHORIZED);
    }

    public static ApiException forbidden() {
        return new ApiException(40301, "forbidden", HttpStatus.FORBIDDEN);
    }

    public static ApiException notFound(int code, String message) {
        return new ApiException(code, message, HttpStatus.NOT_FOUND);
    }

    public static ApiException conflict(int code, String message) {
        return new ApiException(code, message, HttpStatus.CONFLICT);
    }
}
