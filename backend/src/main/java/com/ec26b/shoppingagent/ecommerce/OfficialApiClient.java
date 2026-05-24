package com.ec26b.shoppingagent.ecommerce;

import java.util.List;

public interface OfficialApiClient {
    String platform();

    boolean configured();

    List<OfficialProductResult> search(ProductSourceQuery query);
}
