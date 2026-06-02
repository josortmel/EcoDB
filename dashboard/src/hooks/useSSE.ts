import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { EcodbSseEvent } from '../types/electron';
import { createEventDigest } from '../lib/eventDigest';
import { useAuthStore } from '../stores/auth';
import { useActivityStore } from '../stores/activity';
import { useIngestionStore, type DocStatus } from '../stores/ingestion';
import { useAgentPresence, parseAgentId } from '../stores/presence';

const DOC_EVENTS = new Set<string>(['document_indexed', 'document_failed', 'duplicate_detected']);

const STREAM_PATH = '/api/v1/events/stream';
const BASE_RECONNECT_MS = 2_000;
const MAX_RECONNECT_MS = 60_000;
const STALL_MS = 60_000; // 2× the server's 30s heartbeat

// Subscribes to the org-filtered event stream (via the main-process bridge, NOT
// EventSource). Invalidations are coalesced by the event digest. Reconnects with
// exponential backoff (reset on a healthy connection) and refetches everything
// on reconnect to backfill missed events.
export function useSSE(enabled = true): void {
  const qc = useQueryClient();
  const lastBeat = useRef(Date.now());

  useEffect(() => {
    const bridge = window.ecodb;
    if (!enabled || !bridge) return;

    const digest = createEventDigest((key) => void qc.invalidateQueries({ queryKey: key }));

    let stopped = false;
    let unsub: (() => void) | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const open = () => {
      lastBeat.current = Date.now();
      let connected = false;
      unsub = bridge.sse(STREAM_PATH, (ev: EcodbSseEvent) => {
        lastBeat.current = Date.now();
        if (ev.event === 'error') {
          if (ev.data === 'no_api_key') {
            void useAuthStore.getState().signOut(); // session gone — don't wait for an HTTP 401
            return;
          }
          scheduleReconnect();
          return;
        }
        if (!connected) {
          connected = true;
          attempts = 0; // a real event means the connection is healthy — reset backoff
        }
        if (ev.event === 'heartbeat') return;
        useActivityStore.getState().push(ev.event); // live feed
        if (DOC_EVENTS.has(ev.event)) useIngestionStore.getState().pushDoc(ev.event as DocStatus, ev.data); // ingestion queue
        if (ev.event === 'agent_connected') useAgentPresence.getState().connect(parseAgentId(ev.data) ?? '');
        else if (ev.event === 'agent_disconnected') useAgentPresence.getState().disconnect(parseAgentId(ev.data) ?? '');
        digest.push(ev.event);
      });
    };

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer) return;
      unsub?.();
      unsub = null;
      useAgentPresence.getState().reset(); // presence is stale while disconnected — don't claim online without a live link
      const delay = Math.min(BASE_RECONNECT_MS * 2 ** attempts, MAX_RECONNECT_MS);
      attempts++;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (stopped) return;
        digest.reset(); // drop coalesced pending — the global refresh below covers it
        void qc.invalidateQueries(); // soft refresh: backfill events missed while down
        open();
      }, delay);
    };

    open();

    const watchdog = setInterval(() => {
      if (Date.now() - lastBeat.current > STALL_MS) scheduleReconnect();
    }, 30_000);

    return () => {
      stopped = true;
      unsub?.();
      digest.reset();
      useAgentPresence.getState().reset();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      clearInterval(watchdog);
    };
  }, [qc, enabled]);
}
