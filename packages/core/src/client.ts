import axios, { AxiosInstance } from "axios";
import {
  ExtractionRequest,
  ExtractedFile,
  JobState,
  StartExtractionResponse,
  HealthResponse,
} from "./types";

export class PageCapClient {
  private http: AxiosInstance;
  private baseUrl: string;

  constructor(baseUrl = "http://127.0.0.1:8765") {
    this.baseUrl = baseUrl;
    this.http = axios.create({ baseURL: baseUrl, timeout: 10_000 });
  }

  async health(): Promise<HealthResponse> {
    const res = await this.http.get<HealthResponse>("/health");
    return res.data;
  }

  async startExtraction(request: ExtractionRequest): Promise<StartExtractionResponse> {
    const res = await this.http.post<StartExtractionResponse>("/extract", request);
    return res.data;
  }

  async getJob(jobId: string): Promise<JobState> {
    const res = await this.http.get<JobState>(`/jobs/${jobId}`);
    return res.data;
  }

  async listFiles(jobId: string): Promise<ExtractedFile[]> {
    const res = await this.http.get<{ files: ExtractedFile[] }>(`/jobs/${jobId}/files`);
    return res.data.files;
  }

  async cancelJob(jobId: string): Promise<void> {
    await this.http.delete(`/jobs/${jobId}`);
  }

  downloadUrl(jobId: string, filename: string): string {
    return `${this.baseUrl}/jobs/${jobId}/download/${encodeURIComponent(filename)}`;
  }

  watchJob(
    jobId: string,
    onUpdate: (state: JobState) => void,
    onError?: (err: Event) => void,
  ): WebSocket {
    const wsUrl = this.baseUrl.replace(/^http/, "ws") + `/ws/${jobId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (evt) => {
      try {
        const state: JobState = JSON.parse(evt.data);
        onUpdate(state);
        if (state.status === "done" || state.status === "error" || state.status === "cancelled") {
          ws.close();
        }
      } catch {
        // ignore malformed frames
      }
    };

    if (onError) ws.onerror = onError;
    return ws;
  }
}

export const defaultClient = new PageCapClient();
