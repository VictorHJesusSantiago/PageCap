import axios, { AxiosInstance } from "axios";
import {
  ExtractionRequest,
  ExtractedFile,
  JobState,
  StartExtractionResponse,
  HealthResponse,
  CredentialProfile,
  JobTemplate,
  ScheduleConfig,
} from "./types";

export class PageCapClient {
  private http: AxiosInstance;
  private baseUrl: string;
  private apiToken?: string;

  constructor(baseUrl = "http://127.0.0.1:8765", apiToken?: string) {
    this.baseUrl = baseUrl;
    this.apiToken = apiToken;
    this.http = axios.create({
      baseURL: baseUrl,
      timeout: 10_000,
      headers: apiToken ? { Authorization: `Bearer ${apiToken}` } : undefined,
    });
  }

  private withToken(url: string): string {
    if (!this.apiToken) return url;
    return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(this.apiToken)}`;
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

  async listJobs(): Promise<JobState[]> {
    const res = await this.http.get<{ jobs: JobState[] }>("/jobs");
    return res.data.jobs;
  }

  async cancelJob(jobId: string): Promise<void> {
    await this.http.delete(`/jobs/${jobId}`);
  }

  async pauseJob(jobId: string): Promise<void> {
    await this.http.post(`/jobs/${jobId}/pause`);
  }

  async resumeJob(jobId: string): Promise<void> {
    await this.http.post(`/jobs/${jobId}/resume`);
  }

  downloadUrl(jobId: string, filename: string): string {
    return this.withToken(`${this.baseUrl}/jobs/${jobId}/download/${encodeURIComponent(filename)}`);
  }

  downloadAllUrl(jobId: string): string {
    return this.withToken(`${this.baseUrl}/jobs/${jobId}/download-all`);
  }

  previewUrl(jobId: string, filename: string): string {
    return this.withToken(`${this.baseUrl}/jobs/${jobId}/preview/${encodeURIComponent(filename)}`);
  }

  async saveCredentialProfile(profile: CredentialProfile): Promise<void> {
    await this.http.post("/credentials", profile);
  }

  async listCredentialProfiles(): Promise<CredentialProfile[]> {
    const res = await this.http.get<{ profiles: CredentialProfile[] }>("/credentials");
    return res.data.profiles;
  }

  async deleteCredentialProfile(name: string): Promise<void> {
    await this.http.delete(`/credentials/${encodeURIComponent(name)}`);
  }

  async saveTemplate(template: JobTemplate): Promise<void> {
    await this.http.post("/templates", template);
  }

  async listTemplates(): Promise<JobTemplate[]> {
    const res = await this.http.get<{ templates: JobTemplate[] }>("/templates");
    return res.data.templates;
  }

  async getTemplate(name: string): Promise<JobTemplate> {
    const res = await this.http.get<JobTemplate>(`/templates/${encodeURIComponent(name)}`);
    return res.data;
  }

  async deleteTemplate(name: string): Promise<void> {
    await this.http.delete(`/templates/${encodeURIComponent(name)}`);
  }

  async saveSchedule(schedule: ScheduleConfig): Promise<void> {
    await this.http.post("/schedules", schedule);
  }

  async listSchedules(): Promise<ScheduleConfig[]> {
    const res = await this.http.get<{ schedules: ScheduleConfig[] }>("/schedules");
    return res.data.schedules;
  }

  async deleteSchedule(name: string): Promise<void> {
    await this.http.delete(`/schedules/${encodeURIComponent(name)}`);
  }

  watchJob(
    jobId: string,
    onUpdate: (state: JobState) => void,
    onError?: (err: Event) => void,
  ): WebSocket {
    const wsUrl = this.withToken(this.baseUrl.replace(/^http/, "ws") + `/ws/${jobId}`);
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (evt) => {
      try {
        const state: JobState = JSON.parse(evt.data);
        onUpdate(state);
        if (state.status === "done" || state.status === "error" || state.status === "cancelled") {
          ws.close();
        }
      } catch {
        return;
      }
    };

    if (onError) ws.onerror = onError;
    return ws;
  }
}

export const defaultClient = new PageCapClient();
