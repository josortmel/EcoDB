import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPut, apiDelete } from '../lib/api';
import { assertNodeId } from './ontology';

export interface ApiKey {
  id: number;
  name: string;
  active: boolean;
  grace_until?: string | null;
}

export interface RotateResponse {
  new_key_id: number;
  new_api_key: string;
  old_key_id: number;
  grace_until?: string | null;
}

// GET /auth/api-keys — super/CEO only (403 otherwise; handled in the UI).
export function useApiKeys() {
  return useQuery({ queryKey: ['auth', 'api-keys'], queryFn: () => apiGet<ApiKey[]>('/auth/api-keys') });
}

// POST /auth/api-keys/{id}/rotate — returns the new plaintext key ONCE.
export function useRotateKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => {
      assertNodeId(id);
      return apiPost<RotateResponse>(`/auth/api-keys/${id}/rotate`, {});
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['auth', 'api-keys'] }),
  });
}

// ── Entity dictionary (super/CEO) — /admin/entity-dictionary ──
export interface DictEntity {
  id: number;
  name: string;
  entity_type: string;
  notes?: string | null;
}
export interface DictEntityInput {
  name: string;
  entity_type: string;
  notes?: string;
}

const DICT_KEY = ['admin', 'entity-dictionary'];

export function useEntityDictionary(enabled = true) {
  return useQuery({ queryKey: DICT_KEY, queryFn: () => apiGet<DictEntity[]>('/admin/entity-dictionary'), enabled });
}
export function useSaveEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: DictEntityInput }) =>
      id == null ? apiPost<DictEntity>('/admin/entity-dictionary', body) : apiPut<DictEntity>(`/admin/entity-dictionary/${id}`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: DICT_KEY }),
  });
}
export function useDeleteEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => {
      assertNodeId(id);
      return apiDelete<unknown>(`/admin/entity-dictionary/${id}`);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: DICT_KEY }),
  });
}

// ── Graph vocabulary (super/CEO) — /admin/graph-vocabulary ──
// The rich ontology view (Ontology Console) reads this; the basic
// entity-dictionary CRUD lives in Settings.
export interface VocabEntity {
  name: string;
  type: string;
}
export interface VocabPredicate {
  name: string;
  description: string;
  state?: PredicateState;
  cluster?: string;
}
export interface GraphVocabulary {
  entities: VocabEntity[];
  predicates: VocabPredicate[];
  entity_count: number;
  predicate_count: number;
}

const VOCAB_KEY = ['admin', 'graph-vocabulary'];

export function useGraphVocabulary(enabled = true) {
  return useQuery({ queryKey: VOCAB_KEY, queryFn: () => apiGet<GraphVocabulary>('/admin/graph-vocabulary'), enabled });
}

// ── Predicates CRUD (super) — /admin/predicates (#44) ──
// The list comes from graph-vocabulary, which returns state + cluster per
// predicate, so an edit pre-fills the current state.
export type PredicateState = 'experimental' | 'candidate' | 'approved' | 'deprecated' | 'archived' | 'forbidden';
export const PREDICATE_STATES: PredicateState[] = ['experimental', 'candidate', 'approved', 'deprecated', 'archived', 'forbidden'];

export interface PredicateInput {
  name: string;
  description?: string;
  cluster?: string;
  state?: PredicateState;
}

export function useCreatePredicate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PredicateInput) => apiPost<unknown>('/admin/predicates', body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: VOCAB_KEY }),
  });
}
export function useUpdatePredicate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, body }: { name: string; body: { description?: string; cluster?: string; state?: PredicateState } }) =>
      apiPut<unknown>(`/admin/predicates/${encodeURIComponent(name)}`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: VOCAB_KEY }),
  });
}
export function useDeletePredicate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => apiDelete<unknown>(`/admin/predicates/${encodeURIComponent(name)}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: VOCAB_KEY }),
  });
}

// ── Stop entities (super/CEO) — /admin/stop-entities ──
export interface StopEntity {
  id: number;
  name: string;
  reason?: string | null;
}

const STOP_KEY = ['admin', 'stop-entities'];

export function useStopEntities(enabled = true) {
  return useQuery({ queryKey: STOP_KEY, queryFn: () => apiGet<StopEntity[]>('/admin/stop-entities'), enabled });
}
export function useCreateStopEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; reason?: string }) => apiPost<StopEntity>('/admin/stop-entities', body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: STOP_KEY }),
  });
}
export function useDeleteStopEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => {
      assertNodeId(id);
      return apiDelete<unknown>(`/admin/stop-entities/${id}`);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: STOP_KEY }),
  });
}
