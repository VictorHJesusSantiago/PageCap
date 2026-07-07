import React, { useMemo, useState } from "react";
import { ExtractedFile } from "@pagecap/core";
import { Download, FileText, Film, Music, Image, File, FolderOpen, Archive, X, CheckSquare, Square } from "lucide-react";
import styles from "./FileList.module.css";

interface Props {
  files: ExtractedFile[];
  outputDir?: string;
  getDownloadUrl: (filename: string) => string;
  getPreviewUrl: (filename: string) => string;
  getDownloadAllUrl: () => string;
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

// Media that can render inline in a preview modal without a plugin.
const PREVIEWABLE = new Set(["image", "video", "audio"]);

export function FileList({ files, outputDir, getDownloadUrl, getPreviewUrl, getDownloadAllUrl, onReset }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [previewFile, setPreviewFile] = useState<ExtractedFile | null>(null);

  const filtered = useMemo(
    () => files.filter((f) => filter === "all" || getFileCategory(f.content_type) === filter),
    [files, filter],
  );

  const totalSize = files.reduce((sum, f) => sum + (f.size_bytes ?? 0), 0);

  const toggleSelect = (filename: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  };

  const allFilteredSelected = filtered.length > 0 && filtered.every((f) => selected.has(f.filename));
  const toggleSelectAll = () => {
    setSelected((prev) => {
      if (allFilteredSelected) {
        const next = new Set(prev);
        filtered.forEach((f) => next.delete(f.filename));
        return next;
      }
      const next = new Set(prev);
      filtered.forEach((f) => next.add(f.filename));
      return next;
    });
  };

  // Browsers block rapid programmatic downloads if fired in the same tick;
  // stagger them slightly so every selected file actually starts saving.
  const downloadSelected = () => {
    const names = Array.from(selected);
    names.forEach((filename, i) => {
      setTimeout(() => {
        const a = document.createElement("a");
        a.href = getDownloadUrl(filename);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
      }, i * 250);
    });
  };

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
          <a className={styles.zipBtn} href={getDownloadAllUrl()} title="Baixar tudo como .zip">
            <Archive size={13} /> Baixar tudo
          </a>
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

      {filtered.length > 0 && (
        <div className={styles.selectionBar}>
          <button type="button" className={styles.selectAllBtn} onClick={toggleSelectAll}>
            {allFilteredSelected ? <CheckSquare size={14} /> : <Square size={14} />}
            Selecionar todos
          </button>
          {selected.size > 0 && (
            <button type="button" className={styles.downloadSelectedBtn} onClick={downloadSelected}>
              <Download size={13} /> Baixar {selected.size} selecionado{selected.size !== 1 ? "s" : ""}
            </button>
          )}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className={styles.empty}>Nenhum arquivo deste tipo.</div>
      ) : (
        <div className={styles.list}>
          {filtered.map((file, i) => {
            const category = getFileCategory(file.content_type);
            const canPreview = PREVIEWABLE.has(category);
            return (
              <div key={i} className={styles.item}>
                <button
                  type="button"
                  className={styles.checkbox}
                  onClick={() => toggleSelect(file.filename)}
                  title="Selecionar"
                >
                  {selected.has(file.filename) ? <CheckSquare size={16} /> : <Square size={16} />}
                </button>

                {file.thumbnail && (
                  <img src={file.thumbnail} alt="" className={styles.thumb} loading="lazy" />
                )}
                <span className={styles.icon} data-cat={category}>
                  {FILE_ICONS[category] ?? FILE_ICONS.other}
                </span>
                <div
                  className={`${styles.info} ${canPreview ? styles.infoClickable : ""}`}
                  onClick={() => canPreview && setPreviewFile(file)}
                >
                  <span className={styles.filename}>{file.filename}</span>
                  <span className={styles.meta}>
                    {file.content_type} · {formatBytes(file.size_bytes)}
                    {file.converted_ext && ` · convertido para ${file.converted_ext}`}
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
            );
          })}
        </div>
      )}

      {previewFile && (
        <div className={styles.previewOverlay} onClick={() => setPreviewFile(null)}>
          <div className={styles.previewModal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.previewHeader}>
              <span className={styles.previewTitle}>{previewFile.filename}</span>
              <button type="button" className={styles.previewClose} onClick={() => setPreviewFile(null)}>
                <X size={18} />
              </button>
            </div>
            <div className={styles.previewBody}>
              {getFileCategory(previewFile.content_type) === "image" && (
                <img src={getPreviewUrl(previewFile.filename)} alt={previewFile.filename} className={styles.previewImg} />
              )}
              {getFileCategory(previewFile.content_type) === "video" && (
                <video src={getPreviewUrl(previewFile.filename)} controls autoPlay className={styles.previewMedia} />
              )}
              {getFileCategory(previewFile.content_type) === "audio" && (
                <audio src={getPreviewUrl(previewFile.filename)} controls autoPlay className={styles.previewAudio} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
