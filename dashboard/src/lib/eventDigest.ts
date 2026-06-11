// Coalesces SSE-driven query invalidations so a burst of events doesn't trigger
// a refetch storm. Policy per event type:
//   immediate — low-frequency / high-relevance, invalidate now
//   batch 10s — ingestion bursts, one flush per fixed window
//   debounce 3s — collapse rapid repeats, flush after quiet

// Backend event names (DASHBOARD_BACKEND_GUIDE.md §6). Adding a name here forces
// a config entry below (the Record is exhaustive) — no silent drift / no-op.
export type SseEventName =
  | 'memory_created'
  | 'search_completed'
  | 'contradiction_detected'
  | 'agent_connected'
  | 'agent_disconnected'
  | 'document_indexed'
  | 'document_failed'
  | 'duplicate_detected'
  // Metacognition (v1.3) — emitted on the SAME /events/stream broadcast (no new
  // SSE endpoint; auth inherited from the bridge). Drive the Memory Agent tabs.
  | 'cell.run.started'
  | 'cell.run.completed'
  | 'cell.run.failed'
  | 'cluster.created'
  | 'foresight.triggered';

type Policy = 'immediate' | 'batch' | 'debounce';

interface EventConfig {
  policy: Policy;
  keys: string[][];
}

// Single source of truth: each event's policy AND the query keys it touches.
const EVENTS: Record<SseEventName, EventConfig> = {
  memory_created: {
    policy: 'batch',
    keys: [
      ['stats', 'memories'],
      ['memories', 'recent'],
      ['stats', 'timeline'],
    ],
  },
  // ['documents'] refreshes the historical list; ['document'] (prefix) refreshes
  // an open detail panel + its chunks so it doesn't go stale after the SSE event.
  document_indexed: {
    policy: 'batch',
    keys: [
      ['stats', 'memories'],
      ['inbox', 'summary'],
      ['documents'],
      ['document'],
    ],
  },
  document_failed: { policy: 'batch', keys: [['inbox', 'summary'], ['documents'], ['document']] },
  duplicate_detected: {
    policy: 'batch',
    keys: [
      ['inbox', 'summary'],
      ['stats', 'knowledge'],
      ['documents'],
      ['document'],
    ],
  },
  search_completed: { policy: 'debounce', keys: [['stats', 'search']] },
  contradiction_detected: { policy: 'immediate', keys: [['inbox', 'summary']] },
  // The online dots come from the SSE presence store, not this query — so the
  // roster only needs to catch up. Debounce collapses a connect/disconnect burst
  // into one refetch instead of N immediate ones.
  agent_connected: { policy: 'debounce', keys: [['stats', 'agents']] },
  agent_disconnected: { policy: 'debounce', keys: [['stats', 'agents']] },

  // ── Memory Agent (v1.3) ──
  // A run starting just adds a row to the telemetry list — immediate, low-freq.
  'cell.run.started': { policy: 'immediate', keys: [['ma', 'cell-runs']] },
  // A run completing can emit a burst of cluster.created alongside it (a
  // consolidation writes many clusters) — debounce so the burst is one refetch.
  'cell.run.completed': {
    policy: 'debounce',
    keys: [
      ['ma', 'cell-runs'],
      ['ma', 'cell-health'],
      ['ma', 'clusters'],
      ['ma', 'briefing'],
    ],
  },
  // Failures matter now — surface immediately in telemetry + health.
  'cell.run.failed': { policy: 'immediate', keys: [['ma', 'cell-runs'], ['ma', 'cell-health']] },
  // Consolidation creates clusters in bursts → debounce; refreshes the cluster
  // list and the briefing's pending_clusters.
  'cluster.created': { policy: 'debounce', keys: [['ma', 'clusters'], ['ma', 'briefing']] },
  // A new foresight changes what the briefing shows — immediate, low-freq.
  'foresight.triggered': { policy: 'immediate', keys: [['ma', 'briefing']] },
};

export const BATCH_MS = 10_000;
export const DEBOUNCE_MS = 3_000;

export interface EventDigest {
  push(eventType: string): void;
  /** Drop pending buckets/timers without flushing (the global reconnect
   *  invalidation already covers everything). Reusable afterwards. */
  reset(): void;
}

const keyId = (k: string[]): string => JSON.stringify(k); // avoids segment-with-space collisions

// NOTE: `invalidate` MUST NOT call push() synchronously — that would re-enter a
// flush while iterating the bucket.
export function createEventDigest(invalidate: (key: string[]) => void): EventDigest {
  const batch = new Map<string, string[]>();
  const debounce = new Map<string, string[]>();
  let batchTimer: ReturnType<typeof setTimeout> | null = null;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  const add = (bucket: Map<string, string[]>, keys: string[][]) => {
    for (const k of keys) bucket.set(keyId(k), k); // dedup by serialized key
  };

  const flush = (bucket: Map<string, string[]>) => {
    for (const k of bucket.values()) invalidate(k);
    bucket.clear();
  };

  const push = (eventType: string) => {
    const cfg = EVENTS[eventType as SseEventName];
    if (!cfg) return;
    switch (cfg.policy) {
      case 'immediate':
        // keys within a single event are already unique — no bucket needed
        for (const k of cfg.keys) invalidate(k);
        break;
      case 'batch':
        add(batch, cfg.keys);
        if (!batchTimer) {
          batchTimer = setTimeout(() => {
            batchTimer = null;
            flush(batch);
          }, BATCH_MS);
        }
        break;
      case 'debounce':
        add(debounce, cfg.keys);
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          debounceTimer = null;
          flush(debounce);
        }, DEBOUNCE_MS);
        break;
    }
  };

  const reset = () => {
    if (batchTimer) clearTimeout(batchTimer);
    if (debounceTimer) clearTimeout(debounceTimer);
    batchTimer = null;
    debounceTimer = null;
    batch.clear();
    debounce.clear();
  };

  return { push, reset };
}
