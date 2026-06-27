export type ContentType =
  | "all"
  | "page_pdf"
  | "images"
  | "videos"
  | "audio"
  | "documents";

export type AuthMethod =
  | "none"
  | "credentials"
  | "cookies"
  | "cookies_browser";

export type CookiesBrowser =
  | "chrome"
  | "firefox"
  | "edge"
  | "brave"
  | "opera"
  | "safari";

export type JobStatus =
  | "queued"
  | "running"
  | "waiting_captcha"
  | "done"
  | "error"
  | "cancelled";

export interface AuthConfig {
  method: AuthMethod;
  username?: string;
  password?: string;
  cookies_raw?: string;
  cookies_browser?: CookiesBrowser;
  cookies_profile?: string;
  manual_captcha?: boolean;
}

export interface ExtractionRequest {
  url: string;
  content_types?: ContentType[];
  auth?: AuthConfig;
  output_dir?: string;
  max_depth?: number;
  max_files?: number;
  follow_links?: boolean;
  quality?: "best" | "worst";
  network_wait?: number;
  screen_record?: boolean;
  screen_record_duration?: number;
}

export interface ExtractedFile {
  filename: string;
  url: string;
  content_type: string;
  size_bytes?: number;
  local_path?: string;
  thumbnail?: string;
}

export interface JobState {
  job_id: string;
  status: JobStatus;
  url: string;
  progress: number;
  total: number;
  message: string;
  files: ExtractedFile[];
  error?: string;
  output_dir?: string;
}

export interface StartExtractionResponse {
  job_id: string;
  status: string;
}

export interface HealthResponse {
  status: string;
  version: string;
}
