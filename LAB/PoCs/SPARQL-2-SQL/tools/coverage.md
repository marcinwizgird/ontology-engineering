| feature | compiles | runs on DuckDB | matches oracle | note |
|---|---|---|---|---|
| IRI in the result | yes | yes | yes | 8 rows |
| superclass of a superclass (LegalPerson) | yes | yes | yes | 8 rows |
| DISTINCT | yes | yes | yes | 3 rows |
| LIMIT / OFFSET | yes | yes | yes | 3 rows |
| COUNT + GROUP BY | yes | yes | yes | 2 rows |
| UNION | yes | yes | yes | 8 rows |
| FILTER regex | yes | yes | yes | 2 rows |
| FILTER NOT EXISTS | yes | yes | yes | 4 rows |
| MINUS | yes | yes | yes | 8 rows |
| BIND + CONCAT | yes | yes | yes | 13 rows |
| VALUES | yes | yes | yes | 2 rows |
| property path (/) | yes | yes | yes | 9 rows |
| subquery | yes | yes | **no** | SQL 6 rows vs oracle 8 -- the SQL is right: GROUP BY ?c yields only the 6 companies with reports; rdflib evaluates the subquery correlated with the outer ?c and adds 2 rows with an unbound total |
| unbound predicate (?p) | yes | yes | yes | 42 rows |
