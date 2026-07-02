# Starter deployment artifacts

**Illustrative, not production-ready.** These manifests/values show *how* the
requirements (`../REQUIREMENTS_CATALOG.md`) map to concrete Kubernetes/Helm
configuration on GKE. Replace every `REPLACE` / `PROJECT` / `REGION` placeholder,
pin image digests, and validate sizing by load test before use.

| File | What | Key requirements |
|---|---|---|
| `falkordb/values.yaml` | Helm values for FalkorDB on the Bitnami Redis chart (replication + Sentinel, persistence, auth/TLS, module load-time flags, mem-optimised pool) | TR.PG.01,03,04,05,06,07,09,10 + TR.CN.06 |
| `fuseki/fuseki-statefulset.yaml` | Single-writer Fuseki StatefulSet (RWO SSD PVC, bounded heap, non-root, NetworkPolicy, PDB) | TR.SK.01,02,03,04,07,08; TR.CN.04,05 |
| `fuseki/config-tdb2.ttl` | Fuseki assembler: TDB2 dataset, split read/update/admin endpoints, query timeout, optional Lucene text index | TR.SK.04,06,07,10 |

## Apply (sketch)

```bash
# namespace + secrets (via External Secrets / Secret Manager) assumed to exist
kubectl -n knowledge-graph create configmap fuseki-config --from-file=fuseki/config-tdb2.ttl
kubectl apply -f fuseki/fuseki-statefulset.yaml

helm install falkordb oci://registry-1.docker.io/bitnamicharts/redis \
  -n knowledge-graph -f falkordb/values.yaml
```

Not included here (covered as proposals in `../requirements/supporting-components.md`):
Gateway/IAP, External Secrets, RDF Delta + projection service, OntoOps pipeline,
backup CronJobs, observability wiring. Add these per your platform standards.
