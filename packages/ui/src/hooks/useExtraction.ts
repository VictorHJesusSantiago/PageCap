import { useCallback, useRef, useState } from "react";
import { ExtractionRequest, JobState } from "@pagecap/core";
import { client } from "../apiClient";

export type ExtractionPhase = "idle" | "starting" | "running" | "done" | "error";

export interface UseExtractionResult {
  phase: ExtractionPhase;
  job: JobState | null;
  start: (req: ExtractionRequest) => Promise<void>;
  cancel: () => void;
  reset: () => void;
  downloadUrl: (filename: string) => string;
  downloadAllUrl: () => string;
  previewUrl: (filename: string) => string;
  loadJob: (jobId: string) => Promise<void>;
  pause: () => void;
  resume: () => void;
}

function phaseForStatus(status: JobState["status"]): ExtractionPhase {
  if (status === "done" || status === "cancelled") return "done";
  if (status === "error") return "error";
  return "running"; // queued | running | waiting_captcha
}

export function useExtraction(): UseExtractionResult {
  const [phase, setPhase] = useState<ExtractionPhase>("idle");
  const [job, setJob] = useState<JobState | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const currentJobId = useRef<string | null>(null);

  const watch = useCallback((jobId: string) => {
    wsRef.current?.close();
    wsRef.current = client.watchJob(
      jobId,
      (state) => {
        setJob({ ...state });
        setPhase(phaseForStatus(state.status));
      },
      () => setPhase("error"),
    );
  }, []);

  const start = useCallback(async (req: ExtractionRequest) => {
    if (phase !== "idle") return;
    setPhase("starting");
    setJob(null);

    try {
      const { job_id } = await client.startExtraction(req);
      currentJobId.current = job_id;
      setPhase("running");
      watch(job_id);
    } catch (err) {
      setPhase("error");
      setJob((prev) => ({
        ...(prev ?? { job_id: "", url: req.url, progress: 0, total: 0, files: [], message: "", status: "error", created_at: Date.now() / 1000, updated_at: Date.now() / 1000 }),
        error: err instanceof Error ? err.message : "Erro ao conectar com a API. O servidor está rodando?",
        status: "error",
      }));
    }
  }, [phase, watch]);

  const cancel = useCallback(() => {
    if (currentJobId.current) {
      client.cancelJob(currentJobId.current).catch(() => {});
    }
    wsRef.current?.close();
    setPhase("idle");
  }, []);

  const pause = useCallback(() => {
    if (currentJobId.current) {
      client.pauseJob(currentJobId.current).catch(() => {});
    }
  }, []);

  const resume = useCallback(() => {
    if (currentJobId.current) {
      client.resumeJob(currentJobId.current).catch(() => {});
    }
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

  const downloadAllUrl = useCallback(() => {
    return currentJobId.current ? client.downloadAllUrl(currentJobId.current) : "#";
  }, []);

  const previewUrl = useCallback((filename: string) => {
    return currentJobId.current ? client.previewUrl(currentJobId.current, filename) : "#";
  }, []);

  // Loads a job from history into the current view. If it's still in
  // flight, reconnect the WebSocket so it keeps updating live; otherwise
  // just render its final state.
  const loadJob = useCallback(async (jobId: string) => {
    const state = await client.getJob(jobId);
    currentJobId.current = jobId;
    setJob(state);
    setPhase(phaseForStatus(state.status));
    if (state.status === "queued" || state.status === "running" || state.status === "waiting_captcha") {
      watch(jobId);
    }
  }, [watch]);

  return { phase, job, start, cancel, reset, downloadUrl, downloadAllUrl, previewUrl, loadJob, pause, resume };
}
