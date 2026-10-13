package com.acme.ar;

import java.math.BigDecimal;

public class Calc2 {
    public BigDecimal calcAmt2(BigDecimal amt, BigDecimal rt, long d) {
        BigDecimal perDay = rt.divide(new BigDecimal("365"), 10, BigDecimal.ROUND_HALF_UP);
        return amt.multiply(perDay).multiply(new BigDecimal(d));
    }
}
