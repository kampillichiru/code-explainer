package com.acme.ar;

import java.sql.*;

public class CustDao {
    private Connection con;

    public Cust find(String id) {
        try {
            PreparedStatement ps = con.prepareStatement(
                "SELECT TYP, RT, REG, EXEMPT_FLG FROM CUST_MASTER WHERE CUST_ID = ? AND STS = 'A'");
            ps.setString(1, id);
            ResultSet rs = ps.executeQuery();
            if (!rs.next()) {
                return null;
            }
            Cust c = new Cust();
            c.typ = rs.getString(1);
            c.rt = rs.getBigDecimal(2);
            c.reg = rs.getInt(3);
            c.exFlg = "Y".equals(rs.getString(4));
            return c;
        } catch (SQLException e) {
            return null;
        }
    }
}
