-- Nightly clean-up of small balances
CREATE OR REPLACE PROCEDURE ar_writeoff_small(p_run_date IN DATE) AS
  v_limit NUMBER := 2.50;
BEGIN
  UPDATE AR_INVOICE
     SET STS = 'W', WRITEOFF_DT = p_run_date
   WHERE STS = 'O'
     AND BAL_AMT > 0
     AND BAL_AMT <= v_limit
     AND DUE_DT < p_run_date - 90;

  IF SQL%ROWCOUNT > 1000 THEN
    ROLLBACK;
    RAISE_APPLICATION_ERROR(-20001, 'too many write-offs');
  END IF;
  COMMIT;
EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    RAISE;
END;
/

UPDATE CUST_MASTER SET STS = 'I' WHERE LAST_INV_DT < ADD_MONTHS(SYSDATE, -36) AND STS = 'A';
