package com.acme.ar;

import java.util.Date;

public class Util {
    public static long days(Date a, Date b) {
        long ms = b.getTime() - a.getTime();
        return ms <= 0 ? 0 : ms / 86400000L;
    }
}
