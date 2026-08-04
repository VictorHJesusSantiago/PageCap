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
  | "paused"
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

  credential_profile?: string;

  totp_secret?: string;
}

export interface ExtractionRequest {
  url: string;
  content_types?: ContentType[];
  target_extensions?: string[];
  auth?: AuthConfig;
  output_dir?: string;
  max_files?: number;
  quality?: "best" | "worst";
  network_wait?: number;
  screen_record?: boolean;
  screen_record_duration?: number;
  convert_to?: string;

  follow_links?: boolean;
  max_depth?: number;

  use_sitemap?: boolean;

  max_pages?: number;

  wait_selector?: string;

  click_selector?: string;
  click_max_times?: number;

  min_file_size_bytes?: number;

  url_pattern?: string;

  metadata_only?: boolean;

  download_concurrency?: number;

  download_retries?: number;

  dedupe_by_hash?: boolean;

  convert_rules?: Record<string, string>;

  zip_output?: boolean;

  additional_urls?: string[];

  wait_until?: "load" | "domcontentloaded" | "networkidle" | "commit";
  wait_timeout_ms?: number;

  headless?: boolean | null;

  expected_hashes?: Record<string, string>;

  download_priority?: string[];

  max_file_size_bytes?: number;
  max_job_size_bytes?: number;

  webhook_url?: string;

  blocked_domains?: string[];

  scan_with_clamav?: boolean;

  verify_mime?: boolean;

  export_structured_data_csv?: boolean;

  generate_thumbnails?: boolean;
}

export interface ExtractedFile {
  filename: string;
  url: string;
  content_type: string;
  size_bytes?: number;
  local_path?: string;
  thumbnail?: string;
  converted_path?: string;
  converted_ext?: string;
  content_hash?: string;
  duplicate_of?: string;
  hash_verified?: boolean | null;
  mime_mismatch?: boolean;
  clamav_clean?: boolean | null;
}

export interface FileProgress {
  filename: string;
  bytes_done: number;
  bytes_total?: number | null;
}

export interface DiffResult {
  compared_to_job_id: string;
  added: string[];
  removed: string[];
  changed: string[];
  unchanged_count: number;
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
  created_at: number;
  updated_at: number;
  zip_path?: string;
  current_file?: FileProgress | null;
  diff?: DiffResult | null;
  paywall_warning?: string | null;
}

export interface StartExtractionResponse {
  job_id: string;
  status: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
  jobs_total: number;
  jobs_active: number;
  jobs_done: number;
  jobs_error: number;
  error_rate: number;
  avg_duration_seconds: number;
  db_path: string;
  job_ttl_seconds: number;
}

export interface CredentialProfile {
  name: string;
  domain: string;
  username: string;

  password?: string;
  totp_secret?: string;
  created_at?: number;
}

export interface JobTemplate {
  name: string;
  request: ExtractionRequest;
  created_at?: number;
}

export interface ScheduleConfig {
  schedule_id?: string;
  name: string;
  request: ExtractionRequest;
  interval_seconds: number;
  enabled?: boolean;
  next_run_at?: number;
  last_job_id?: string;
  created_at?: number;
}
