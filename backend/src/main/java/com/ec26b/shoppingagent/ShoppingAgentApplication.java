package com.ec26b.shoppingagent;

import com.ec26b.shoppingagent.config.LocalDotEnv;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShoppingAgentApplication {
    public static void main(String[] args) {
        LocalDotEnv.load();
        SpringApplication.run(ShoppingAgentApplication.class, args);
    }
}
