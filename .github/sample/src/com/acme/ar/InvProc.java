package com.acme.ar;

import java.math.BigDecimal;
import java.util.Date;

public class InvProc {

    private CustDao dao = new CustDao();
    private Calc2 c2 = new Calc2();

    public BigDecimal procA(String custId, BigDecimal amt, Date due, Date now) {
        Cust c = dao.find(custId);
        if (c == null) {
            throw new IllegalArgumentException("no customer");
        }
        BigDecimal tot = amt;
        long d = Util.days(due, now);
        int grace = "G".equals(c.typ) ? 15 : 5;
        if (d > grace && !c.exFlg) {
            tot = tot.add(c2.calcAmt2(amt, c.rt, d));
        }
        tot = tot.add(tx(amt, c));
        return tot.setScale(2, BigDecimal.ROUND_HALF_UP);
    }

    private BigDecimal tx(BigDecimal amt, Cust c) {
        switch (c.reg) {
            case 1:
                return amt.multiply(new BigDecimal("0.18"));
            case 2:
                return amt.multiply(new BigDecimal("0.05"));
            default:
                return BigDecimal.ZERO;
        }
    }

    private void oldPost(BigDecimal amt) {
        if (amt.signum() < 0) {
            System.out.println("neg");
        }
    }
}
