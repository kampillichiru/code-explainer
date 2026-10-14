import java.io.BufferedReader;
import java.io.FileDescriptor;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.PrintStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.List;

/**
 * Runs methods of the module with the inputs of the worked examples and prints what they return.
 * Used by run_check.py. It is compiled into the output folder, never into the source folders.
 *
 * Input: a text file, one field per line, fields separated by a tab:
 *   CASE id / CLASS full.class.Name / METHOD name / ARG type value (once for each parameter) / RUN
 * Output, one line for each case:
 *   RESULT id VALUE text | RESULT id NULL | RESULT id THROWS ExceptionName message | RESULT id ERROR text
 * A case that runs longer than the limit (second argument, in seconds) gives RESULT id TIMEOUT and ends the run.
 */
public class ExplainerHarness {

    private static final String DATE_FORMAT = "yyyy-MM-dd HH:mm:ss";
    private static volatile String running = null;
    private static volatile long deadline = Long.MAX_VALUE;

    public static void main(String[] argv) throws Exception {
        PrintStream out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, "UTF-8");
        PrintStream quiet = new PrintStream(new OutputStream() {
            public void write(int b) {
            }
        });
        System.setOut(quiet);  // what the code under test prints is not a result
        System.setErr(quiet);

        final PrintStream report = out;
        final long limit = (argv.length > 1 ? Long.parseLong(argv[1]) : 20L) * 1000L;
        Thread watchdog = new Thread() {  // code that never ends must not keep this process alive
            public void run() {
                while (true) {
                    try {
                        Thread.sleep(100);
                    } catch (InterruptedException e) {
                        return;
                    }
                    String id = running;
                    if (id != null && System.currentTimeMillis() > deadline) {
                        report.println("RESULT\t" + id + "\tTIMEOUT");
                        report.flush();
                        Runtime.getRuntime().halt(3);
                    }
                }
            }
        };
        watchdog.setDaemon(true);
        watchdog.start();

        BufferedReader in = new BufferedReader(new InputStreamReader(new FileInputStream(argv[0]), "UTF-8"));
        String id = null, cls = null, method = null;
        List<String> types = new ArrayList<String>();
        List<String> values = new ArrayList<String>();
        String line;
        while ((line = in.readLine()) != null) {
            String[] f = line.split("\t", 3);
            if (f[0].equals("CASE")) {
                id = f[1];
                types.clear();
                values.clear();
            } else if (f[0].equals("CLASS")) {
                cls = f[1];
            } else if (f[0].equals("METHOD")) {
                method = f[1];
            } else if (f[0].equals("ARG")) {
                types.add(f[1]);
                values.add(f.length > 2 ? f[2] : "");
            } else if (f[0].equals("RUN")) {
                out.println("START\t" + id);
                String result;
                deadline = System.currentTimeMillis() + limit;
                running = id;
                try {
                    result = run(cls, method, types, values);
                } catch (Throwable t) {
                    result = "ERROR\t" + escape(String.valueOf(t));
                }
                running = null;
                out.println("RESULT\t" + id + "\t" + result);
            }
        }
        in.close();
        out.flush();
        System.exit(0);  // the code under test may have left a thread running
    }

    private static String run(String cls, String method, List<String> types, List<String> values) throws Throwable {
        Class<?> c = Class.forName(cls);
        Method found = null;
        for (Method m : c.getDeclaredMethods()) {
            Class<?>[] p = m.getParameterTypes();
            if (!m.getName().equals(method) || p.length != types.size()) {
                continue;
            }
            boolean same = true;
            for (int i = 0; i < p.length; i++) {
                same = same && p[i].getSimpleName().equals(types.get(i));
            }
            if (same) {
                found = m;
            }
        }
        if (found == null) {
            return "ERROR\tmethod not found";
        }
        Class<?>[] p = found.getParameterTypes();
        Object[] args = new Object[p.length];
        for (int i = 0; i < p.length; i++) {
            args[i] = convert(p[i], values.get(i));
        }
        found.setAccessible(true);
        Object target = null;
        if (!Modifier.isStatic(found.getModifiers())) {
            Constructor<?> k = c.getDeclaredConstructor();
            k.setAccessible(true);
            target = k.newInstance();
        }
        try {
            Object r = found.invoke(target, args);
            return r == null ? "NULL" : "VALUE\t" + escape(show(r));
        } catch (InvocationTargetException e) {
            Throwable t = e.getCause();
            return "THROWS\t" + t.getClass().getSimpleName() + "\t" + escape(String.valueOf(t.getMessage()));
        }
    }

    private static Object convert(Class<?> t, String raw) throws Exception {
        if (raw.equals("\\N")) {
            if (t.isPrimitive()) {
                throw new IllegalArgumentException("no value for " + t.getSimpleName());
            }
            return null;
        }
        String v = unescape(raw);
        if (t == String.class) return v;
        if (t == int.class || t == Integer.class) return Integer.valueOf(v);
        if (t == long.class || t == Long.class) return Long.valueOf(v);
        if (t == double.class || t == Double.class) return Double.valueOf(v);
        if (t == float.class || t == Float.class) return Float.valueOf(v);
        if (t == short.class || t == Short.class) return Short.valueOf(v);
        if (t == byte.class || t == Byte.class) return Byte.valueOf(v);
        if (t == boolean.class || t == Boolean.class) return Boolean.valueOf(v);
        if (t == char.class || t == Character.class) return Character.valueOf(v.charAt(0));
        if (t == BigDecimal.class) return new BigDecimal(v);
        if (t == BigInteger.class) return new BigInteger(v);
        if (java.util.Date.class.isAssignableFrom(t)) {
            SimpleDateFormat f = new SimpleDateFormat(DATE_FORMAT);
            f.setLenient(false);
            long ms = f.parse(v).getTime();
            if (t == java.sql.Date.class) return new java.sql.Date(ms);
            if (t == java.sql.Timestamp.class) return new java.sql.Timestamp(ms);
            if (t == java.util.Date.class) return new java.util.Date(ms);
        }
        throw new IllegalArgumentException("type not supported: " + t.getName());
    }

    private static String show(Object r) {
        if (r instanceof BigDecimal) return ((BigDecimal) r).toPlainString();
        if (r instanceof java.util.Date) return new SimpleDateFormat(DATE_FORMAT).format((java.util.Date) r);
        return String.valueOf(r);
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r");
    }

    private static String unescape(String s) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (ch == '\\' && i + 1 < s.length()) {
                char n = s.charAt(++i);
                b.append(n == 't' ? '\t' : n == 'n' ? '\n' : n == 'r' ? '\r' : n);
            } else {
                b.append(ch);
            }
        }
        return b.toString();
    }
}
