/** Shared display formatters.
 *
 * `formatBytes` lived in both FileList and ProgressPanel with one meaningful
 * difference: a falsy size means "unknown" in a file listing but "nothing
 * transferred yet" in a progress readout. That difference is now a parameter
 * rather than a reason to keep two copies drifting apart.
 */

const KB = 1024;
const MB = KB * 1024;

export function formatBytes(bytes?: number | null, fallback = "?"): string {
  if (!bytes) return fallback;
  if (bytes < KB) return `${bytes} B`;
  if (bytes < MB) return `${(bytes / KB).toFixed(1)} KB`;
  return `${(bytes / MB).toFixed(2)} MB`;
}

/** Category used for icon choice and preview eligibility. Mirrors the server's
 * inline allowlist in engine/api.py — keep the two in step. */
export function getFileCategory(contentType: string): string {
  if (contentType.includes("pdf")) return "pdf";
  if (contentType.startsWith("image/")) return "image";
  if (contentType.startsWith("video/")) return "video";
  if (contentType.startsWith("audio/")) return "audio";
  if (
    contentType.includes("word") ||
    contentType.includes("excel") ||
    contentType.includes("powerpoint") ||
    contentType.includes("spreadsheet") ||
    contentType.includes("presentation")
  ) {
    return "document";
  }
  return "other";
}
