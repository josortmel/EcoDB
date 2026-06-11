import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPut, apiDelete } from '../lib/api';
import { assertUuid, assertIntId } from '../lib/assertUuid';

// ============================================================================
// Memory Agent — data layer (EcoDB v1.3, Spec §2).
//
// All hooks call the real API (schema 5.3.0). Shapes verified against
// curl openapi.json during reconciliation: CellTaskConfig, PromptTemplate,
// AgentSummary, ProviderKey.api_key_masked, ClusterSearchResult, telescopic.
//
// Path prefix: /api/v1 for the metacognition routers (clusters, briefing,
// cells, agents, providers).
// ============================================================================

const V1 = '/api/v1';

// ---------------------------------------------------------------------------
// Shared shapes (Spec §2)
// ---------------------------------------------------------------------------

export type ClusterLevel = 'weekly' | 'monthly' | 'quarterly' | 'yearly';
export type ClusterStatus = 'candidate' | 'active' | 'rejected' | 'superseded';

export interface ClusterSummary {
  id: string;
  agent_id: number;
  level: ClusterLevel;
  label: string;
  detail?: string | null;
  narrative?: string | null;
  member_count: number;
  source_count: number;
  pattern_flags: Record<string, unknown>;
  period_start: string;
  period_end: string;
  status: ClusterStatus;
  narrated_at?: string | null;
  created_at: string;
}

export interface ClusterMember {
  memory_id: string;
  content: string;
  tags: string[];
  type: string;
  created_at: string;
  distances: Record<string, number>;
}

export interface ClusterSearchResult {
  id: string;
  level: string;
  label: string;
  narrative_preview: string;
  agent_identifier: string;
  period_start: string;
  period_end: string;
  member_count: number;
  vector_score: number;
  bm25_score: number;
}

export interface ClusterNarrativeSummary {
  id: string;
  label: string;
  narrative: string;
  period_start: string;
  period_end: string;
  member_count: number;
  source_count: number;
}

// ---------------------------------------------------------------------------
// Briefing (Spec §2 — REAL, v2.0)
// ---------------------------------------------------------------------------

export interface ForesightItem {
  memory_id: string;
  content: string;
  foresight_start: string;
  foresight_end: string;
  urgency_score: number;
  evidence?: string | null; // backend may return null/empty — consumers guard (BC3)
}

export interface TensionItem {
  id: string;
  observed_trait: string;
  declared_trait: string;
  tension_type: string;
  evidence_memory_ids: string[];
  created_at: string;
  status: string;
}

export interface TelescopicSummary {
  weeklies: ClusterSummary[];
  monthlies: ClusterSummary[];
  quarterlies: ClusterSummary[];
  yearlies: ClusterSummary[];
}

export interface BriefingResponse {
  agent_identifier: string;
  foresights: ForesightItem[];
  identity_tensions: TensionItem[];
  pending_clusters: ClusterSummary[];
  telescopic_summary: TelescopicSummary;
}

export function useBriefing(agentIdentifier: string, enabled = true) {
  return useQuery({
    queryKey: ['ma', 'briefing', agentIdentifier],
    queryFn: () => apiGet<BriefingResponse>(`${V1}/briefing?agent_identifier=${encodeURIComponent(agentIdentifier)}`),
    enabled: enabled && agentIdentifier.length > 0,
  });
}

export function useDismissForesight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ memoryId, reason }: { memoryId: string; reason: string }) => {
      assertUuid(memoryId); // server-issued id flows into the path — validate + encode (VS1)
      return apiPut<unknown>(`${V1}/briefing/foresights/${encodeURIComponent(memoryId)}/dismiss`, { reason });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'briefing'] }),
  });
}

// tensionId is the tension's own id (tensions are stored as memories, so it is a
// memory UUID). Param renamed from memoryId for clarity (IC1/AU1).
export function useDismissTension() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tensionId, reason }: { tensionId: string; reason: string }) => {
      assertUuid(tensionId); // VS2
      return apiPut<unknown>(`${V1}/briefing/tensions/${encodeURIComponent(tensionId)}/dismiss`, { reason });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'briefing'] }),
  });
}

// ---------------------------------------------------------------------------
// Cell telemetry (Spec §2 — REAL, v2.0)
// ---------------------------------------------------------------------------

export interface CellRun {
  id: string; // the run's uuid (GET /cells/runs returns `id`, not `run_id`)
  cell_type: string;
  agent_identifier?: string | null;
  model: string;
  prompt_version?: string | null;
  started_at: string;
  finished_at?: string | null;
  status: string;
  tokens_used?: number | null;
  cost_usd?: number | null;
  items_created: number;
  errors: unknown[];
  metrics: Record<string, unknown>;
}

export interface CellRunsResponse {
  items: CellRun[];
  total: number;
  cursor_next?: string | null;
}

export interface CellHealth {
  last_run_by_type: Record<string, string | null>;
  errors_24h: number;
  total_cost_30d?: number | null;
}

export function useCellRuns(params: { cellType?: string; agentIdentifier?: string; limit?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.cellType) qs.set('cell_type', params.cellType);
  if (params.agentIdentifier) qs.set('agent_identifier', params.agentIdentifier);
  qs.set('limit', String(params.limit ?? 20));
  return useQuery({
    queryKey: ['ma', 'cell-runs', params.cellType ?? '', params.agentIdentifier ?? '', params.limit ?? 20],
    queryFn: () => apiGet<CellRunsResponse>(`${V1}/cells/runs?${qs.toString()}`),
  });
}

export function useCellHealth() {
  return useQuery({
    queryKey: ['ma', 'cell-health'],
    queryFn: () => apiGet<CellHealth>(`${V1}/cells/health`),
  });
}

// ---------------------------------------------------------------------------
// Clusters — list / detail / members / sources / narrate / status (REAL, v2.0)
// ---------------------------------------------------------------------------

export interface ClustersListResponse {
  items: ClusterSummary[];
  total: number;
  cursor_next?: string | null;
}

export function useClusters(params: { agentIdentifier: string; level?: ClusterLevel; status?: ClusterStatus; limit?: number }) {
  const qs = new URLSearchParams();
  qs.set('agent_identifier', params.agentIdentifier);
  if (params.level) qs.set('level', params.level);
  if (params.status) qs.set('status', params.status);
  qs.set('limit', String(params.limit ?? 20));
  return useQuery({
    queryKey: ['ma', 'clusters', params.agentIdentifier, params.level ?? '', params.status ?? '', params.limit ?? 20],
    queryFn: () => apiGet<ClustersListResponse>(`${V1}/clusters?${qs.toString()}`),
    enabled: params.agentIdentifier.length > 0,
  });
}

export function useCluster(clusterId: string | null) {
  return useQuery({
    queryKey: ['ma', 'cluster', clusterId],
    queryFn: () => {
      assertUuid(clusterId!); // enabled gate guarantees non-null; validate + encode (VS3)
      return apiGet<ClusterSummary & { metadata: Record<string, unknown> }>(`${V1}/clusters/${encodeURIComponent(clusterId!)}`);
    },
    enabled: !!clusterId,
  });
}

export interface ClusterMembersResponse {
  cluster_id: string;
  members: ClusterMember[];
  total: number;
  cursor_next?: string | null;
}

export function useClusterMembers(clusterId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['ma', 'cluster-members', clusterId],
    queryFn: () => {
      assertUuid(clusterId!); // VS3
      return apiGet<ClusterMembersResponse>(`${V1}/clusters/${encodeURIComponent(clusterId!)}/members`);
    },
    enabled: enabled && !!clusterId,
  });
}

export interface ClusterSourcesResponse {
  cluster_id: string;
  sources: ClusterSummary[];
  parent_clusters: ClusterSummary[];
}

export function useClusterSources(clusterId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['ma', 'cluster-sources', clusterId],
    queryFn: () => {
      assertUuid(clusterId!); // VS3
      return apiGet<ClusterSourcesResponse>(`${V1}/clusters/${encodeURIComponent(clusterId!)}/sources`);
    },
    enabled: enabled && !!clusterId,
  });
}

export function useNarrateCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ clusterId, narrative }: { clusterId: string; narrative: string }) => {
      assertUuid(clusterId); // VS3
      return apiPut<unknown>(`${V1}/clusters/${encodeURIComponent(clusterId)}/narrate`, { narrative });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['ma', 'clusters'] });
      void qc.invalidateQueries({ queryKey: ['ma', 'cluster'] }); // refresh an open drawer detail in place
    },
  });
}

export function useSetClusterStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ clusterId, status, reason }: { clusterId: string; status: 'active' | 'rejected' | 'superseded'; reason?: string }) => {
      assertUuid(clusterId); // VS3 — destructive (status mutation), validate + encode
      return apiPut<unknown>(`${V1}/clusters/${encodeURIComponent(clusterId)}/status`, reason ? { status, reason } : { status });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['ma', 'clusters'] });
      void qc.invalidateQueries({ queryKey: ['ma', 'cluster'] });
      void qc.invalidateQueries({ queryKey: ['ma', 'briefing'] }); // pending_clusters may change
    },
  });
}

// ---------------------------------------------------------------------------
// Cluster search (Spec §2  POST /clusters/search)
// ---------------------------------------------------------------------------

export interface ClusterSearchResponse {
  results: ClusterSearchResult[];
  count: number;
  duration_ms: number;
}

export function useClusterSearch() {
  return useMutation({
    mutationFn: (body: { query_text: string; agent_identifier?: string; level?: string; status?: string; limit?: number }) =>
      apiPost<ClusterSearchResponse>(`${V1}/clusters/search`, body),
  });
}

// ---------------------------------------------------------------------------
// Telescopic view (Spec §2  GET /clusters/telescopic)
// ---------------------------------------------------------------------------

export interface TelescopicResponse {
  agent_identifier: string;
  weekly: ClusterNarrativeSummary[];
  monthly: ClusterNarrativeSummary[];
  quarterly: ClusterNarrativeSummary[];
  yearly: ClusterNarrativeSummary[];
}

export function useTelescopicView(agentIdentifier: string, levels = 'weekly,monthly,quarterly,yearly', enabled = true) {
  return useQuery({
    queryKey: ['ma', 'telescopic', agentIdentifier, levels],
    queryFn: () =>
      apiGet<TelescopicResponse>(
        `${V1}/clusters/telescopic?agent_identifier=${encodeURIComponent(agentIdentifier)}&levels=${encodeURIComponent(levels)}`,
      ),
    enabled: enabled && agentIdentifier.length > 0,
  });
}

// ---------------------------------------------------------------------------
// Cell task configs (Spec §2  CRUD /cells/configs)
// ---------------------------------------------------------------------------

export interface CellTaskConfig {
  id: number;
  agent_id: number;
  agent_identifier: string;
  cell_type: string;
  enabled: boolean;
  model: string;
  provider: string;
  prompt_template_id?: number | null;
  prompt_template_name?: string | null;
  schedule_cron?: string | null;
  level?: ClusterLevel | null;
  config: Record<string, unknown>;
  last_run?: string | null;
  last_run_status?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CellConfigsResponse {
  items: CellTaskConfig[];
  total: number;
}

export function useCellConfigs(params: { agentIdentifier?: string; cellType?: string; enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['ma', 'cell-configs', params.agentIdentifier ?? '', params.cellType ?? ''],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (params.agentIdentifier) qs.set('agent_identifier', params.agentIdentifier);
      if (params.cellType) qs.set('cell_type', params.cellType);
      return apiGet<CellConfigsResponse>(`${V1}/cells/configs?${qs.toString()}`);
    },
    enabled: params.enabled !== false, // BC1_CFG: lets AgentConfigRow gate on row-open (lazy)
  });
}

export function useCreateCellConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<CellTaskConfig> & { agent_identifier: string; cell_type: string }) =>
      apiPost<CellTaskConfig>(`${V1}/cells/configs`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'cell-configs'] }),
  });
}

export function useUpdateCellConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; body: Partial<CellTaskConfig> }) =>
      apiPut<CellTaskConfig>(`${V1}/cells/configs/${vars.id}`, vars.body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'cell-configs'] }),
  });
}

export function useDeleteCellConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiDelete<unknown>(`${V1}/cells/configs/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'cell-configs'] }),
  });
}

// ---------------------------------------------------------------------------
// Prompt templates (Spec §2  CRUD /cells/templates)
// ---------------------------------------------------------------------------

export interface PromptTemplate {
  id: number;
  name: string;
  cell_type: string;
  content: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface PromptTemplatesResponse {
  items: PromptTemplate[];
  total: number;
}

export function useCellTemplates(cellType?: string) {
  return useQuery({
    queryKey: ['ma', 'cell-templates', cellType ?? ''],
    queryFn: () => apiGet<PromptTemplatesResponse>(`${V1}/cells/templates${cellType ? `?cell_type=${encodeURIComponent(cellType)}` : ''}`),
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; cell_type: string; content: string; is_default?: boolean }) =>
      apiPost<PromptTemplate>(`${V1}/cells/templates`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'cell-templates'] }),
  });
}

export function useUpdateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; body: Partial<{ name: string; content: string; is_default: boolean }> }) => {
      assertIntId(vars.id);
      return apiPut<PromptTemplate>(`${V1}/cells/templates/${vars.id}`, vars.body);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'cell-templates'] }),
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    // 409 when the template is referenced by configs (ApiError surfaces it via errMsg)
    mutationFn: (id: number) => {
      assertIntId(id);
      return apiDelete<unknown>(`${V1}/cells/templates/${id}`);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'cell-templates'] }),
  });
}

// ---------------------------------------------------------------------------
// Agents (Spec §2  GET/POST /agents)
// ---------------------------------------------------------------------------

export interface AgentSummary {
  id: number;
  identifier: string;
  display_name?: string | null;
  description?: string | null;
  active: boolean;
  cognition_class: string;
  last_seen?: string | null;
  cell_configs_count: number;
  clusters_count: number;
  last_cell_run?: string | null;
}

export interface AgentsResponse {
  items: AgentSummary[];
  total: number;
}

export function useAgents() {
  return useQuery({
    queryKey: ['ma', 'agents'],
    queryFn: () => apiGet<AgentsResponse>(`${V1}/agents`),
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { identifier: string; display_name?: string; description?: string; cognition_class?: string }) =>
      apiPost<AgentSummary>(`${V1}/agents`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'agents'] }),
  });
}

// ---------------------------------------------------------------------------
// LLM provider keys (Spec §2  )
// Keys arrive MASKED from GET — the cleartext key never reaches the renderer.
// ---------------------------------------------------------------------------

export interface ProviderKey {
  id: number;
  provider: string;
  display_name?: string | null;
  api_key_masked: string; // e.g. "sk-****…3f2a" — never the cleartext key
  model_default?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProvidersResponse {
  items: ProviderKey[];
  total: number;
}

export function useProviders() {
  return useQuery({
    queryKey: ['ma', 'providers'],
    queryFn: () => apiGet<ProvidersResponse>(`${V1}/providers`),
  });
}

export function useSaveProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { provider: string; api_key: string; model_default?: string; display_name?: string }) =>
      apiPost<ProviderKey>(`${V1}/providers`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'providers'] }),
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiDelete<unknown>(`${V1}/providers/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['ma', 'providers'] }),
  });
}

// ---------------------------------------------------------------------------
// Manual cell trigger (Spec §2 — REAL, v2.0: POST /cells/trigger/{cell_type})
// ---------------------------------------------------------------------------

export function useTriggerCell() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ cellType, agentIdentifier, level, periodStart, periodEnd }: { cellType: string; agentIdentifier: string; level?: ClusterLevel; periodStart?: string; periodEnd?: string }) => {
      const qs = new URLSearchParams();
      qs.set('agent_identifier', agentIdentifier);
      if (level) qs.set('level', level);
      if (periodStart) qs.set('period_start', periodStart);
      if (periodEnd) qs.set('period_end', periodEnd);
      return apiPost<unknown>(`${V1}/cells/trigger/${encodeURIComponent(cellType)}?${qs.toString()}`, {});
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['ma', 'cell-runs'] });
      void qc.invalidateQueries({ queryKey: ['ma', 'cell-health'] });
    },
  });
}

// ---------------------------------------------------------------------------
// Foresights (v1.3 dedicated view — GET /foresights, per-agent).
// agent_identifier is REQUIRED by the endpoint; the query stays disabled until
// an agent is selected. Shape: ForesightItem (openapi).
// ---------------------------------------------------------------------------

export type ForesightStatus = 'active' | 'expired' | 'dismissed';

// ForesightItem is shared with the Briefing section (same backend shape — the
// list endpoint now returns the typed ForesightItem, aligned with briefing).

export interface ForesightsResponse {
  items: ForesightItem[];
  total: number;
  cursor_next: string | null;
}

export function useForesights(agentIdentifier?: string, status?: ForesightStatus) {
  return useQuery({
    queryKey: ['ma', 'foresights', agentIdentifier ?? '', status ?? ''],
    enabled: !!agentIdentifier,
    queryFn: () => {
      const qs = new URLSearchParams({ agent_identifier: agentIdentifier as string });
      if (status) qs.set('status', status);
      return apiGet<ForesightsResponse>(`${V1}/foresights?${qs.toString()}`);
    },
  });
}

// ---------------------------------------------------------------------------
// Skills (v1.3 dedicated view — GET /skills list + /skills/{id} detail +
// PUT /skills/{id}/status). Skill ids are UUIDs (assertUuid on path build).
// ---------------------------------------------------------------------------

export type SkillStatus = 'active' | 'stale' | 'candidate' | 'deprecated';

export interface SkillCard {
  id: string;
  task_signature: string;
  steps: string[];
  tools: string[];
  failure_modes: string[];
  validation_checklist: string[];
  success_rate: number;
  source_case_ids: string[];
  status: SkillStatus;
  created_at: string;
  updated_at: string | null;
}

export interface SkillsResponse {
  items: SkillCard[];
  total: number;
  cursor_next: string | null;
}

// GET /skills/{id} source_cases[] — backend CaseResponse.
export interface SkillSourceCase {
  id: string;
  content: string;
  task_type: string | null;
  steps: string[] | null;
  result: string | null;
  success: boolean | null;
  skill_id: string | null;
  created_at: string;
}

export interface SkillDetail extends SkillCard {
  source_cases: SkillSourceCase[];
}

export function useSkills(agentIdentifier?: string, status?: SkillStatus) {
  return useQuery({
    queryKey: ['ma', 'skills', agentIdentifier ?? '', status ?? ''],
    enabled: !!agentIdentifier,
    queryFn: () => {
      const qs = new URLSearchParams({ agent_identifier: agentIdentifier as string });
      if (status) qs.set('status', status);
      return apiGet<SkillsResponse>(`${V1}/skills?${qs.toString()}`);
    },
  });
}

export function useSkillDetail(skillId?: string) {
  return useQuery({
    queryKey: ['ma', 'skill', skillId ?? ''],
    enabled: !!skillId,
    queryFn: () => {
      assertUuid(skillId as string);
      return apiGet<SkillDetail>(`${V1}/skills/${encodeURIComponent(skillId as string)}`);
    },
  });
}

export function useSetSkillStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; status: SkillStatus }) => {
      assertUuid(vars.id);
      return apiPut<SkillCard>(`${V1}/skills/${encodeURIComponent(vars.id)}/status`, { status: vars.status });
    },
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: ['ma', 'skills'] });
      void qc.invalidateQueries({ queryKey: ['ma', 'skill', vars.id] });
    },
  });
}
