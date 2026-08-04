const KB = 1024;
const MB = KB * 1024;

export function formatBytes(bytes?: number | null, fallback = "?"): string {
  if (!bytes) return fallback;
  if (bytes < KB) return `${bytes} B`;
  if (bytes < MB) return `${(bytes / KB).toFixed(1)} KB`;
  return `${(bytes / MB).toFixed(2)} MB`;
}

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
