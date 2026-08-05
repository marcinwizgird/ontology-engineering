/**
 * fusekiSource.ts -- Playground <-> Fuseki bridge client.
 *
 * Drop this into Ontology-Playground at `src/lib/rdf/fusekiSource.ts`. It talks to the Python
 * proxy (ontology_modeler.playground.api), never to Fuseki directly, so there is no CORS dance
 * and no Fuseki credentials in the browser.
 *
 * The proxy returns/accepts Playground's own `Ontology` shape, extended with two fields the
 * unified projection adds:
 *   - EntityType.kind:   'class' | 'concept'
 *   - Relationship.kind: 'subClassOf' | 'broader' | 'narrower' | 'mapping' | 'objectProperty'
 * See INTEGRATION.md for wiring these into the store and the node/edge renderers.
 */

// If you import Playground's real types, replace these with:  import type { Ontology } from '../../data/ontology';
export type NodeKind = 'class' | 'concept';
export type EdgeKind = 'subClassOf' | 'broader' | 'narrower' | 'mapping' | 'objectProperty';

export interface FusekiOntologyEnvelope {
  graphUri: string;
  ontologyIri: string | null;
  baseNs: string;
  ontology: unknown; // Playground's Ontology (with the extra `kind` fields on nodes/edges)
}

export interface OntologyListing {
  graphUri: string;
  ontologyIri: string | null;
  nodeCount: number;
}

export interface SaveResult {
  graphUri: string;
  method: 'incremental' | 'put' | 'incremental+put-fallback' | 'noop' | 'dry-run';
  added: number;
  removed: number;
  applied: boolean;
  verified: boolean | null;
  baseTriples: number;
  mergedTriples: number;
  dryRun: boolean;
}

/** Raised when the proxy's preservation guard (HTTP 409) refuses a save. */
export class PreservationError extends Error {
  violations: string[];
  constructor(message: string, violations: string[]) {
    super(message);
    this.name = 'PreservationError';
    this.violations = violations;
  }
}

const BASE: string =
  (import.meta as { env?: Record<string, string> }).env?.VITE_FUSEKI_BRIDGE_URL ??
  'http://localhost:8080';

async function asJson(res: Response): Promise<unknown> {
  if (res.status === 409) {
    const body = (await res.json().catch(() => ({}))) as {
      detail?: { message?: string; violations?: string[] };
    };
    throw new PreservationError(
      body.detail?.message ?? 'save refused by preservation guard',
      body.detail?.violations ?? [],
    );
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Fuseki bridge ${res.status}: ${text}`);
  }
  return res.json();
}

export async function bridgeHealthy(): Promise<boolean> {
  try {
    const r = (await asJson(await fetch(`${BASE}/health`))) as { fuseki?: boolean };
    return Boolean(r.fuseki);
  } catch {
    return false;
  }
}

export async function listOntologies(): Promise<OntologyListing[]> {
  return (await asJson(await fetch(`${BASE}/ontologies`))) as OntologyListing[];
}

/** Load a named graph from Fuseki as an editable Playground ontology. */
export async function loadFromFuseki(graphUri: string): Promise<FusekiOntologyEnvelope> {
  const url = `${BASE}/ontology?graph=${encodeURIComponent(graphUri)}`;
  return (await asJson(await fetch(url))) as FusekiOntologyEnvelope;
}

/**
 * Propagate an edited ontology back to its Fuseki named graph. Only the fields the projection
 * surfaced are changed; everything else in the graph is preserved. Pass dryRun to preview the
 * diff (added/removed counts) without writing.
 */
export async function saveToFuseki(
  graphUri: string,
  ontology: unknown,
  opts: { dryRun?: boolean } = {},
): Promise<SaveResult> {
  const url =
    `${BASE}/ontology?graph=${encodeURIComponent(graphUri)}` +
    (opts.dryRun ? '&dryRun=true' : '');
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ontology }),
  });
  return (await asJson(res)) as SaveResult;
}
