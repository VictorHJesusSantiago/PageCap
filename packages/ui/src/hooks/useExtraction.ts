import { useState, useRef, useCallback } from "react";
import { PageCapClient, ExtractionRequest, JobState } from "@pagecap/core";

const API_BASE = (window as any).__PAGECAP_API__ ?? "http://127.0.0.1:8765";
const client = new PageCapClient(API_BASE);

export type ExtractionPhase = "idle" | "starting" | "running" | "done" | "error";

export interface UseExtractionResult {
  phase: ExtractionPhase;
  job: JobState | null;
  start: (req: ExtractionRequest) => Promise<void>;
  cancel: () => void;
  reset: () => void;
  downloadUrl: (filename: string) => string;
}

export function useExtraction(): UseExtractionResult {
  const [phase, setPhase] = useState<ExtractionPhase>("idle");
  const [job, setJob] = useState<JobState | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const currentJobId = useRef<string | null>(null);

  const start = useCallback(async (req: ExtractionRequest) => {
    setPhase("starting");
    setJob(null);

    try {
      const { job_id } = await client.startExtraction(req);
      currentJobId.current = job_id;
      setPhase("running");

      wsRef.current = client.watchJob(
        job_id,
        (state) => {
          setJob({ ...state });
          if (state.status === "done") setPhase("done");
          else if (state.status === "error") setPhase("error");
          else if (state.status === "cancelled") setPhase("idle");
        },
        () => setPhase("error"),
      );
    } catch (err) {
      setPhase("error");
      setJob((prev) => ({
        ...(prev ?? { job_id: "", url: req.url, progress: 0, total: 0, files: [], message: "", status: "error" }),
        error: err instanceof Error ? err.message : "Erro ao conectar com a API. O servidor está rodando?",
        status: "error",
      }));
    }
  }, []);

  const cancel = useCallback(() => {
    if (currentJobId.current) {
      client.cancelJob(currentJobId.current).catch(() => {});
    }
    wsRef.current?.close();
    setPhase("idle");
  }, []);

  const reset = useCallback(() => {
    wsRef.current?.close();
    setPhase("idle");
    setJob(null);
    currentJobId.current = null;
  }, []);

  const downloadUrl = useCallback((filename: string) => {
    return currentJobId.current
      ? client.downloadUrl(currentJobId.current, filename)
      : "#";
  }, []);

  return { phase, job, start, cancel, reset, downloadUrl };
}
