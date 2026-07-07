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
  /** Name of a saved CredentialProfile to resolve username/password/TOTP from. */
  credential_profile?: string;
  /** Base32 TOTP secret — PageCap computes the current code and fills it automatically. */
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
  /** Follow same-domain <a href> links up to max_depth hops from the start URL. */
  follow_links?: boolean;
  max_depth?: number;
  /** Seed extra same-domain pages from /sitemap.xml (or robots.txt Sitemap:). */
  use_sitemap?: boolean;
  /** Hard cap on total pages visited during a crawl. */
  max_pages?: number;
  /** Wait for this CSS selector before scanning (dynamic/SPA content). */
  wait_selector?: string;
  /** "Load more"/"next page" button to click before scanning. */
  click_selector?: string;
  click_max_times?: number;
  /** Skip candidates smaller than this many bytes. */
  min_file_size_bytes?: number;
  /** Regex the candidate asset URL must match. */
  url_pattern?: string;
  /** List assets found without downloading them (files[].local_path stays null). */
  metadata_only?: boolean;
  /** How many files download concurrently. */
  download_concurrency?: number;
  /** Retries (with exponential backoff) per failed download before giving up. */
  download_retries?: number;
  /** Skip saving a file whose content (sha256) matches one already kept in this job. */
  dedupe_by_hash?: boolean;
  /** Per-category conversion template, e.g. {"image": ".webp", "video": ".mp4"}. */
  convert_rules?: Record<string, string>;
  /** Zip every downloaded file into a single archive once the job finishes. */
  zip_output?: boolean;
  /** Extra seed URLs crawled in the same job as the primary `url`. */
  additional_urls?: string[];
  /** Playwright navigation wait strategy + timeout. */
  wait_until?: "load" | "domcontentloaded" | "networkidle" | "commit";
  wait_timeout_ms?: number;
  /** Independent headless override (null/undefined = default heuristic). */
  headless?: boolean | null;
  /** sha256 hashes already known to be correct for specific URLs (url -> hex digest). */
  expected_hashes?: Record<string, string>;
  /** Categories downloaded before any others, e.g. ["image","document"]. */
  download_priority?: string[];
  /** Hard byte caps for a single file / the whole job. */
  max_file_size_bytes?: number;
  max_job_size_bytes?: number;
  /** POST the final JobState JSON to this URL when the job finishes. */
  webhook_url?: string;
  /** Domains that must never be requested. */
  blocked_domains?: string[];
  /** Scan downloaded files with the OS's installed ClamAV (no-op if absent). */
  scan_with_clamav?: boolean;
  /** Cross-check declared Content-Type/extension against magic bytes. */
  verify_mime?: boolean;
  /** Also write structured_data.csv next to structured_data.json. */
  export_structured_data_csv?: boolean;
  /** Generate a small local thumbnail (data: URI) for images/videos. */
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
  /** Only present when saving; GET /credentials never returns this field. */
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
