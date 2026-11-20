"use client";

import { useState, useEffect, useRef, useCallback } from "react";

export type SSEConnectionStatus = "idle" | "connecting" | "connected" | "disconnected" | "ended" | "error";

interface UseSSEOptions {
  enabled?: boolean;
  onEvent?: (event: unknown) => void;
  onEnd?: () => void;
  reconnectAttempts?: number;
  runId?: string;
}

export function useSSE(url: string | null, options: UseSSEOptions = {}) {
  const { enabled = true, onEvent, onEnd, reconnectAttempts = 5, runId } = options;
  const [events, setEvents] = useState<unknown[]>([]);
  const [status, setStatus] = useState<SSEConnectionStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const attemptsRef = useRef(0);
  const seenSignatures = useRef<Set<string>>(new Set());
  const onEventRef = useRef(onEvent);
  const onEndRef = useRef(onEnd);
  
  // Use a ref to store the connect function to break circular dependencies
  const connectRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    onEventRef.current = onEvent;
    onEndRef.current = onEnd;
  }, [onEvent, onEnd]);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    // Only update status if it's not already idle/ended, to avoid unnecessary re-renders
    setStatus((prev) => (prev === "connected" ? "disconnected" : prev));
  }, []);

  const connect = useCallback(async () => {
    if (!url || !enabled) return;

    // Ensure we are disconnected before connecting
    if (eventSourceRef.current) {
        eventSourceRef.current.close();
    }
    
    setStatus("connecting");
    setError(null);

    let connectionUrl = url;

    // Acquire short-lived scoped ticket for EventSource authentication
    try {
      const targetRun = runId || url.match(/\/runs\/([a-zA-Z0-9_\-]+)\//)?.[1];
      if (targetRun) {
        const ticketRes = await fetch(
          `/api/auth/ticket?scope=stream&run_id=${encodeURIComponent(targetRun)}`
        );
        if (ticketRes.ok) {
          const ticketData = await ticketRes.json() as { ticket?: string };
          if (ticketData?.ticket) {
            const sep = connectionUrl.includes("?") ? "&" : "?";
            connectionUrl = `${connectionUrl}${sep}ticket=${encodeURIComponent(ticketData.ticket)}`;
          }
        }
      }
    } catch {
      // In development mode without auth or on network fallback, continue with direct URL
    }

    const es = new EventSource(connectionUrl);
    eventSourceRef.current = es;

    es.onopen = () => {
      setStatus("connected");
      attemptsRef.current = 0;
      setError(null);
    };

    es.onmessage = (e) => {
      if (!e.data || e.data === ": heartbeat") return;

      try {
        const parsed = JSON.parse(e.data) as Record<string, unknown>;

        // Deduplication signature
        const sig = `${parsed.event_type || parsed.to_state || "ev"}-${parsed.step_number ?? ""}-${parsed.timestamp ?? ""}-${parsed.description ?? ""}`;
        if (sig && seenSignatures.current.has(sig)) {
          return;
        }
        if (sig) seenSignatures.current.add(sig);

        setEvents((prev) => [...prev, parsed]);
        if (onEventRef.current) {
          onEventRef.current(parsed);
        }

        // Terminal event detection
        const isTerminal =
          parsed.event_type === "stream_end" ||
          parsed.event_type === "completed" ||
          parsed.event_type === "cancelled" ||
          (parsed.event_type === "run_end" && parsed.status) ||
          ["VERIFIED", "FAILED", "UNRESOLVED", "CANCELLED"].includes(parsed.to_state as string);

        if (isTerminal) {
          setStatus("ended");
          es.close();
          if (onEndRef.current) {
            onEndRef.current();
          }
        }
            } catch {
        console.warn("Failed to parse SSE line:", e.data);
      }
    };

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        setStatus("disconnected");
      } else {
        setStatus("error");
      }

      es.close();

      // Attempt reconnection if not ended and below max attempts
      if (attemptsRef.current < reconnectAttempts) {
        attemptsRef.current += 1;
        const delay = Math.min(1000 * Math.pow(1.5, attemptsRef.current), 10000);
        setTimeout(() => {
          if (eventSourceRef.current === es && connectRef.current) {
            connectRef.current();
          }
        }, delay);
      } else {
        setError("Connection lost. Maximum reconnection attempts reached.");
      }
    };
  }, [url, enabled, reconnectAttempts, runId]);

  // Update the ref whenever connect changes
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    if (enabled && url) {
      // Defer connection to avoid triggering state updates in the render phase
      const id = setTimeout(() => connect(), 0);
      return () => clearTimeout(id);
    } else {
      if (status !== "idle") {
        setTimeout(() => {
            disconnect();
            setStatus("idle");
        }, 0);
      }
    }

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [url, enabled, connect, disconnect, status]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    seenSignatures.current.clear();
  }, []);

  return {
    events,
    status,
    error,
    reconnect: connect,
    disconnect,
    clearEvents
  };
}
