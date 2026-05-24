package com.ec26b.shoppingagent.ecommerce;

public class OfficialApiException extends IllegalStateException {
    private static final long serialVersionUID = 1L;

    private final String errorCode;

    public OfficialApiException(String errorCode, String message) {
        super(message);
        this.errorCode = errorCode == null ? "" : errorCode;
    }

    public String errorCode() {
        return errorCode;
    }
}
