import React, { useState } from "react";
import { ExtractedFile } from "@pagecap/core";
import { Download, FileText, Film, Music, Image, File, FolderOpen } from "lucide-react";
import styles from "./FileList.module.css";

interface Props {
  files: ExtractedFile[];
  outputDir?: string;
  getDownloadUrl: (filename: string) => string;
  onReset: () => void;
}

type Filter = "all" | "pdf" | "image" | "video" | "audio" | "document";

const FILE_ICONS: Record<string, React.ReactNode> = {
  pdf: <FileText size={16} />,
  image: <Image size={16} />,
  video: <Film size={16} />,
  audio: <Music size={16} />,
  document: <File size={16} />,
  other: <File size={16} />,
};

function getFileCategory(ct: string): string {
  if (ct.includes("pdf")) return "pdf";
  if (ct.startsWith("image/")) return "image";
  if (ct.startsWith("video/")) return "video";
  if (ct.startsWith("audio/")) return "audio";
  if (ct.includes("word") || ct.includes("excel") || ct.includes("powerpoint") || ct.includes("spreadsheet") || ct.includes("presentation")) return "document";
  return "other";
}

function formatBytes(b?: number): string {
  if (!b) return "?";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(2)} MB`;
}

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "pdf", label: "PDF" },
  { value: "image", label: "Imagens" },
  { value: "video", label: "Vídeos" },
  { value: "audio", label: "Áudio" },
  { value: "document", label: "Documentos" },
];

export function FileList({ files, outputDir, getDownloadUrl, onReset }: Props) {
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = files.filter((f) => {
    if (filter === "all") return true;
    return getFileCategory(f.content_type) === filter;
  });

  const totalSize = files.reduce((sum, f) => sum + (f.size_bytes ?? 0), 0);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2 className={styles.title}>
            {files.length} arquivo{files.length !== 1 ? "s" : ""} extraído{files.length !== 1 ? "s" : ""}
          </h2>
          <span className={styles.totalSize}>{formatBytes(totalSize)} total</span>
        </div>
        <div className={styles.headerRight}>
          {outputDir && (
            <span className={styles.outDir} title={outputDir}>
              <FolderOpen size={13} /> {outputDir}
            </span>
          )}
          <button className={styles.resetBtn} onClick={onReset}>
            Nova extração
          </button>
        </div>
      </div>

      <div className={styles.filters}>
        {FILTERS.map((f) => (
          <button
            key={f.value}
            className={`${styles.filterBtn} ${filter === f.value ? styles.filterActive : ""}`}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
            <span className={styles.filterCount}>
              {f.value === "all" ? files.length : files.filter((x) => getFileCategory(x.content_type) === f.value).length}
            </span>
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className={styles.empty}>Nenhum arquivo deste tipo.</div>
      ) : (
        <div className={styles.list}>
          {filtered.map((file, i) => (
            <div key={i} className={styles.item}>
              {file.thumbnail && (
                <img src={file.thumbnail} alt="" className={styles.thumb} loading="lazy" />
              )}
              <span className={styles.icon} data-cat={getFileCategory(file.content_type)}>
                {FILE_ICONS[getFileCategory(file.content_type)] ?? FILE_ICONS.other}
              </span>
              <div className={styles.info}>
                <span className={styles.filename}>{file.filename}</span>
                <span className={styles.meta}>
                  {file.content_type} · {formatBytes(file.size_bytes)}
                </span>
              </div>
              <a
                href={getDownloadUrl(file.filename)}
                download={file.filename}
                className={styles.downloadBtn}
                target="_blank"
                rel="noreferrer"
              >
                <Download size={14} />
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
