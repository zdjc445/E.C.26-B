package com.ec26b.shoppingagent;

import com.ec26b.shoppingagent.config.LocalDotEnv;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShoppingAgentApplication {
    public static void main(String[] args) {
        LocalDotEnv.load();
        normalizeDebugFlag();
        SpringApplication.run(ShoppingAgentApplication.class, args);
    }

    static void normalizeDebugFlag() {
        if (System.getProperty("debug") != null) {
            return;
        }
        String debugEnv = System.getenv("DEBUG");
        if (debugEnv != null
                && !debugEnv.equalsIgnoreCase("true")
                && !debugEnv.equalsIgnoreCase("1")
                && !debugEnv.equalsIgnoreCase("yes")
                && !debugEnv.equalsIgnoreCase("on")) {
            System.setProperty("debug", "false");
        }
    }
}
