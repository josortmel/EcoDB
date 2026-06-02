// Mirrors the Pydantic response models (DASHBOARD_BACKEND_GUIDE.md §6 + design.md §4).
// Stats shapes marked "provisional" are confirmed against the live API at 6.25b.
import type { AuthUser } from '../stores/auth';

export type AuthMe = AuthUser;

// ── Search (POST /search) ──
export interface ScoreBreakdown {
  semantic: number;
  graph: number;
  weight: number;
  freshness: number;
  bm25: number;
}

export interface SearchResult {
  id: string;
  user_id: number | null;
  agent_identifier: string | null;
  workspace_id: number;
  project_id: number;
  type: string;
  content_type: string;
  visibility: string;
  content: string;
  tags: string[];
  weight: number;
  score: number;
  semantic_score: number;
  graph_score: number;
  freshness_score: number;
  score_breakdown: ScoreBreakdown;
  matched_modality: string;
  media_path: string | null;
  created_at: string;
  source_type: 'memory' | 'document_chunk';
  // document_chunk results carry the parent document's id (null for memories) —
  // used to open the chunk's source document in the preview drawer.
  document_id: string | null;
  trust_warnings: string[];
}

export interface SearchResponse {
  query: string;
  query_type: string;
  results: SearchResult[];
  count: number;
  limit: number;
  duration_ms: number;
  graph_context: unknown[];
  contradictions: unknown[];
  warnings: string[];
  audit_id: string | null;
}

export interface SearchRequest {
  query_text: string;
  limit?: number;
  include_documents?: boolean;
  max_document_results?: number;
  agent_identifier?: string | null;
  tags?: string[];
  workspace_id?: number | null;
  project_id?: number | null;
  // Ultrasearch (LOCKED preset): graph_discovery true + deep_factor 4.
  graph_discovery?: boolean;
  deep_factor?: number;
}

// ── Recent memories (GET /memories/recent) ──
export interface RecentMemory {
  id: string;
  ts: string;
  content: string;
  type: string;
  tags: string[];
  agent_identifier: string | null;
  staleness?: string;
}

export interface RecentMemoriesResponse {
  items: RecentMemory[];
  total: number;
}

// ── Attention inbox (GET /admin/attention-inbox/*) ──
export type InboxClass = 'stale_memories' | 'pending_alias_candidates' | 'unconfirmed_relations' | 'low_trust_documents';

export interface InboxSummary {
  classes: Record<InboxClass, number>;
  total: number;
}

export interface InboxDetailItem {
  id: string;
  content: string;
  type: string;
  staleness: string;
  created_at: string;
  updated_at: string;
  agent_identifier: string | null;
}

export interface InboxDetailsResponse {
  class: InboxClass;
  total: number;
  items: InboxDetailItem[];
  limit: number;
  offset: number;
}

// ── Timeline (GET /api/v1/stats/timeline?period=30) ──
export interface TimelineDay {
  date: string;
  memories: number;
  documents: number;
  searches: number;
}

export interface TimelineResponse {
  period_days: number;
  timeline: TimelineDay[];
}

// ── Graph (GET /graph/*) ──
export interface GraphNode {
  id: number;
  name: string;
  type: string;
  degree: number;
  cluster_id?: number;
}

export interface GraphEdge {
  source: number;
  target: number;
  predicate: string;
}

export interface SubgraphResponse {
  center: string;
  depth: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated?: boolean;
  total_nodes?: number;
  shown_nodes?: number;
}

// GET /graph/all — whole graph, nodes by degree DESC. clusters/cluster_id ignored.
export interface GraphAllResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  node_count: number;
  edge_count: number;
  limit: number;
  offset: number;
}

export interface NeighborsResponse {
  center: string;
  depth: number;
  neighbors: string[];
}

// ── Stats (GET /api/v1/stats/*) — real shapes verified live at 6.25b (the guide
// was incomplete; the OpenAPI is the contract). ──
export interface MemoryStats {
  period?: string;
  group_by?: string;
  data: { label: string; count: number }[];
  total: number;
}

export interface GraphStats {
  nodes_total: number;
  triples_total: number;
  daily?: { date: string; nodes_created: number; triples_created: number }[];
}

export interface AgentStat {
  identifier: string;
  memories_created: number;
  searches: number;
  last_activity: string | null;
}
export interface AgentStats {
  period?: string;
  agents: AgentStat[];
}

export interface SearchStats {
  available?: boolean;
  period?: string;
  total_queries: number;
  failed_count?: number;
  avg_latency_ms?: number | null;
  p95_latency_ms?: number | null;
}

export interface TopEntity {
  id: number;
  name: string;
  type: string;
  degree: number;
}
export interface KnowledgeStats {
  entity_count: number;
  merged_entity_count?: number;
  alias_candidate_count?: number;
  merge_count?: number;
  orphan_entity_count: number;
  stale_memory_count: number;
  dormant_memory_count: number;
  duplicate_candidate_count: number;
  graph_density: number;
  top_entities_by_degree: TopEntity[];
}

// Real /api/v1/stats/system (verified live).
export interface SystemStats {
  embeddings?: {
    status?: string;
    model_loaded?: boolean;
    quantization?: string;
    cpu_percent?: number;
    vram_used_gb?: number | null;
    vram_total_gb?: number | null;
  };
  db?: { memories_count?: number; nodes_count?: number; triples_count?: number };
  media?: { files_count?: number };
}

// ── Documents (GET /documents, /documents/{id}, /documents/{id}/chunks) — real
// shapes from the live OpenAPI. ──
export interface DocumentListItem {
  id: string;
  uri: string;
  filename: string;
  doc_type: string;
  workspace_id: number;
  project_id: number;
  status: string;
  created_at: string;
}
export interface DocumentDetail extends DocumentListItem {
  visibility: string;
  retry_count: number;
  processing_started_at?: string | null;
  last_indexed?: string | null;
  processing_metrics?: Record<string, unknown> | null;
  base_weight: number;
}
export interface DocumentChunk {
  chunk_index: number;
  content: string;
  section_path?: string | null;
}
export interface DocumentChunksResponse {
  document_id: string;
  chunks: DocumentChunk[];
  chunks_returned: number;
  total_chunks: number;
  truncated: boolean;
}

// ── Workspaces / Projects (GET /workspaces, /workspaces/{id}/projects) — used by
// the Explorer advanced-search scope selectors. ──
export interface Workspace {
  id: number;
  organization_id: number | null;
  name: string;
  created_at: string;
}
export interface WorkspacesResponse {
  items: Workspace[];
}
export interface Project {
  id: number;
  workspace_id: number;
  name: string;
  is_common: boolean;
  created_at: string;
}
export interface ProjectsResponse {
  items: Project[];
  total: number;
}
