import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import it.unibz.inf.ontop.answering.reformulation.QueryReformulator;
import it.unibz.inf.ontop.evaluator.QueryContext;
import it.unibz.inf.ontop.injection.OntopSQLOWLAPIConfiguration;
import it.unibz.inf.ontop.iq.IQ;
import it.unibz.inf.ontop.iq.IQTree;
import it.unibz.inf.ontop.iq.node.ConstructionNode;
import it.unibz.inf.ontop.iq.node.NativeNode;
import it.unibz.inf.ontop.iq.node.QueryNode;
import it.unibz.inf.ontop.model.term.Constant;
import it.unibz.inf.ontop.model.term.ImmutableFunctionalTerm;
import it.unibz.inf.ontop.model.term.ImmutableTerm;
import it.unibz.inf.ontop.model.term.Variable;
import it.unibz.inf.ontop.query.KGQuery;
import com.google.common.collect.ImmutableMap;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Offline Ontop reformulation sidecar.
 *
 * <p>Ontop's stock endpoint serves {@code /ontop/reformulate} only after opening a JDBC
 * connection (verified against ontop/ontop 5.5.0: it fails with UnknownHostException when no
 * database is reachable). This server uses the same Ontop jars but only the
 * {@link QueryReformulator}: ontology + R2RML mapping + db-metadata.json in, PostgreSQL SQL
 * out. No JDBC connection is ever opened, so the container can run with no network route to
 * any database.
 *
 * <p>GET or POST {@code /ontop/reformulate?query=...} returns JSON:
 * {@code {"sql": ..., "columns": {var: column}, "projection": [...], "terms": {var: term},
 * "plan": <IQ as text>, "millis": ...}}. {@code terms} describes how each SPARQL variable is
 * built from the SQL columns (IRI templates, literal casts), as a JSON tree.
 */
public final class OfflineReformulator {

    private static QueryReformulator reformulator;

    public static void main(String[] args) throws Exception {
        String dir = env("ONTOP_INPUT_DIR", "/opt/ontop/input");
        long t0 = System.nanoTime();
        OntopSQLOWLAPIConfiguration config = OntopSQLOWLAPIConfiguration.defaultBuilder()
                .ontologyFile(dir + "/" + env("ONTOP_ONTOLOGY", "fibo-subset.ttl"))
                .r2rmlMappingFile(dir + "/" + env("ONTOP_MAPPING", "fiben-mappings.r2rml.ttl"))
                .propertyFile(dir + "/" + env("ONTOP_PROPERTIES", "ontop.properties"))
                .dbMetadataFile(dir + "/" + env("ONTOP_DB_METADATA", "db-metadata.json"))
                .build();
        reformulator = config.loadQueryReformulator();
        System.out.printf("reformulator ready in %d ms (no database connection)%n",
                (System.nanoTime() - t0) / 1_000_000);
        // warm-up, so the first real request does not pay for class loading
        reformulate("SELECT ?s WHERE { ?s a <urn:warmup> }");

        HttpServer server = HttpServer.create(new InetSocketAddress(Integer.parseInt(env("PORT", "8080"))), 0);
        server.createContext("/health", ex -> send(ex, 200, "{\"status\":\"ok\"}"));
        server.createContext("/ontop/reformulate", OfflineReformulator::handle);
        server.setExecutor(java.util.concurrent.Executors.newFixedThreadPool(4));
        server.start();
        System.out.println("listening on " + env("PORT", "8080"));
    }

    private static String env(String k, String d) {
        String v = System.getenv(k);
        return v == null || v.isEmpty() ? d : v;
    }

    private static void handle(HttpExchange ex) throws IOException {
        try {
            String query = param(ex, "query");
            if (query == null || query.isBlank()) {
                send(ex, 400, "{\"error\":\"missing query parameter\"}");
                return;
            }
            send(ex, 200, reformulate(query));
        } catch (Exception e) {
            send(ex, 422, "{\"error\":" + json(e.getClass().getSimpleName() + ": " + e.getMessage()) + "}");
        }
    }

    static String reformulate(String sparql) throws Exception {
        long t0 = System.nanoTime();
        KGQuery<?> q = reformulator.getInputQueryFactory().createSPARQLQuery(sparql);
        QueryContext ctx = reformulator.getQueryContextFactory().create(ImmutableMap.of());
        IQ iq = reformulator.reformulateIntoNativeQuery(q, ctx, reformulator.getQueryLoggerFactory().create(ctx));
        long micros = (System.nanoTime() - t0) / 1000;

        List<ConstructionNode> constructions = new ArrayList<>();
        List<NativeNode> natives = new ArrayList<>();
        List<String> others = new ArrayList<>();
        walk(iq.getTree(), constructions, natives, others);

        StringBuilder out = new StringBuilder("{");
        out.append("\"micros\":").append(micros);
        out.append(",\"plan\":").append(json(iq.toString()));
        out.append(",\"projection\":[");
        boolean first = true;
        for (Variable v : iq.getProjectionAtom().getArguments()) {
            out.append(first ? "" : ",").append(json(v.getName()));
            first = false;
        }
        out.append("]");
        out.append(",\"other_nodes\":[");
        for (int i = 0; i < others.size(); i++) out.append(i == 0 ? "" : ",").append(json(others.get(i)));
        out.append("]");
        if (natives.size() == 1) {
            NativeNode n = natives.get(0);
            out.append(",\"sql\":").append(json(n.getNativeQueryString()));
            out.append(",\"columns\":{");
            first = true;
            for (Map.Entry<Variable, ?> e : n.getColumnNames().entrySet()) {
                out.append(first ? "" : ",").append(json(e.getKey().getName())).append(":")
                   .append(json(e.getValue().toString()));
                first = false;
            }
            out.append("}");
        } else {
            out.append(",\"sql\":null,\"native_nodes\":").append(natives.size());
        }
        out.append(",\"terms\":{");
        first = true;
        if (!constructions.isEmpty()) {
            // the outermost construction node defines the SPARQL variables
            for (Map.Entry<Variable, ImmutableTerm> e : constructions.get(0).getSubstitution().stream()
                    .collect(java.util.stream.Collectors.toMap(Map.Entry::getKey, Map.Entry::getValue,
                            (a, b) -> a, LinkedHashMap::new)).entrySet()) {
                out.append(first ? "" : ",").append(json(e.getKey().getName())).append(":")
                   .append(term(e.getValue()));
                first = false;
            }
        }
        out.append("}}");
        return out.toString();
    }

    private static void walk(IQTree t, List<ConstructionNode> cs, List<NativeNode> ns, List<String> others) {
        QueryNode root = t.getRootNode();
        if (root instanceof ConstructionNode) cs.add((ConstructionNode) root);
        else if (root instanceof NativeNode) ns.add((NativeNode) root);
        else others.add(root.getClass().getSimpleName().replace("Impl", ""));
        for (IQTree c : t.getChildren()) walk(c, cs, ns, others);
    }

    /** A term as a JSON tree: {"var":..} | {"const":..,"type":..} | {"fn":..,"args":[..]}. */
    private static String term(ImmutableTerm t) {
        if (t instanceof Variable) return "{\"var\":" + json(((Variable) t).getName()) + "}";
        if (t instanceof Constant) {
            Constant c = (Constant) t;
            return "{\"const\":" + json(c.getValue()) + ",\"type\":" + json(c.getClass().getSimpleName().replace("Impl", "")) + "}";
        }
        ImmutableFunctionalTerm f = (ImmutableFunctionalTerm) t;
        StringBuilder b = new StringBuilder("{\"fn\":").append(json(f.getFunctionSymbol().getName()))
                .append(",\"class\":").append(json(f.getFunctionSymbol().getClass().getSimpleName()))
                .append(",\"args\":[");
        for (int i = 0; i < f.getTerms().size(); i++) b.append(i == 0 ? "" : ",").append(term(f.getTerm(i)));
        return b.append("]}").toString();
    }

    private static String param(HttpExchange ex, String name) throws IOException {
        String q = ex.getRequestURI().getRawQuery();
        if ("POST".equalsIgnoreCase(ex.getRequestMethod())) {
            try (InputStream in = ex.getRequestBody()) {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                in.transferTo(buf);
                String body = buf.toString(StandardCharsets.UTF_8);
                String ct = String.valueOf(ex.getRequestHeaders().getFirst("Content-Type"));
                if (ct.startsWith("application/sparql-query")) return body;
                q = body;
            }
        }
        if (q == null) return null;
        for (String kv : q.split("&")) {
            int i = kv.indexOf('=');
            if (i > 0 && kv.substring(0, i).equals(name))
                return URLDecoder.decode(kv.substring(i + 1), StandardCharsets.UTF_8);
        }
        return null;
    }

    private static void send(HttpExchange ex, int status, String body) throws IOException {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "application/json");
        ex.sendResponseHeaders(status, b.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(b);
        }
    }

    static String json(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        return b.append('"').toString();
    }
}
