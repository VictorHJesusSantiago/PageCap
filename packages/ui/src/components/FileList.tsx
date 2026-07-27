import React, { useCallback, useMemo, useState } from "react";
import { ExtractedFile } from "@pagecap/core";
import { Download, FileText, Film, Music, Image, File, FolderOpen, Archive, X, CheckSquare, Square } from "lucide-react";
import { useModalA11y } from "../hooks/useModalA11y";
import { formatBytes, getFileCategory } from "../format";
import { useI18n } from "../i18n";
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

const FILTERS: { value: Filter; labelKey: string }[] = [
  { value: "all", labelKey: "filterAll" },
  { value: "pdf", labelKey: "filterPdf" },
  { value: "image", labelKey: "filterImage" },
  { value: "video", labelKey: "filterVideo" },
  { value: "audio", labelKey: "filterAudio" },
  { value: "document", labelKey: "filterDocument" },
];

// Media that can render inline in a preview modal without a plugin. Mirrors
// the server's inline allowlist in api.py — anything else is served as an
// attachment, so offering a preview for it would just download the file.
const PREVIEWABLE = new Set(["image", "video", "audio"]);

// Browsers block rapid programmatic downloads fired in the same tick.
const DOWNLOAD_STAGGER_MS = 250;

export function FileList({ files, outputDir, getDownloadUrl, getPreviewUrl, getDownloadAllUrl, onReset }: Props) {
  const { t } = useI18n();
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [previewFile, setPreviewFile] = useState<ExtractedFile | null>(null);

  const closePreview = useCallback(() => setPreviewFile(null), []);
  const dialogRef = useModalA11y(previewFile !== null, closePreview);

  const filtered = useMemo(
    () => files.filter((f) => filter === "all" || getFileCategory(f.content_type) === filter),
    [files, filter],
  );

  const countsByCategory = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const f of files) {
      const cat = getFileCategory(f.content_type);
      counts[cat] = (counts[cat] ?? 0) + 1;
    }
    return counts;
  }, [files]);

  const totalSize = useMemo(
    () => files.reduce((sum, f) => sum + (f.size_bytes ?? 0), 0),
    [files],
  );

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
      const next = new Set(prev);
      filtered.forEach((f) => (allFilteredSelected ? next.delete(f.filename) : next.add(f.filename)));
      return next;
    });
  };

  const downloadSelected = () => {
    Array.from(selected).forEach((filename, i) => {
      setTimeout(() => {
        const a = document.createElement("a");
        a.href = getDownloadUrl(filename);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
      }, i * DOWNLOAD_STAGGER_MS);
    });
  };

  const previewCategory = previewFile ? getFileCategory(previewFile.content_type) : null;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2 className={styles.title}>
            {files.length} {t("filesExtracted")}
          </h2>
          <span className={styles.totalSize}>{formatBytes(totalSize)} {t("totalSize")}</span>
        </div>
        <div className={styles.headerRight}>
          {outputDir && (
            <span className={styles.outDir} title={`${t("outputFolder")}: ${outputDir}`}>
              <FolderOpen size={13} aria-hidden="true" /> {outputDir}
            </span>
          )}
          <a className={styles.zipBtn} href={getDownloadAllUrl()}>
            <Archive size={13} aria-hidden="true" /> {t("downloadAll")}
          </a>
          <button type="button" className={styles.resetBtn} onClick={onReset}>
            {t("newExtraction")}
          </button>
        </div>
      </div>

      {/* role=group + aria-pressed makes this read as a filter toggle set
          rather than six unrelated buttons. */}
      <div className={styles.filters} role="group" aria-label={t("whatToExtract")}>
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={filter === f.value}
            className={`${styles.filterBtn} ${filter === f.value ? styles.filterActive : ""}`}
            onClick={() => setFilter(f.value)}
          >
            {t(f.labelKey)}
            <span className={styles.filterCount}>
              {f.value === "all" ? files.length : countsByCategory[f.value] ?? 0}
            </span>
          </button>
        ))}
      </div>

      {filtered.length > 0 && (
        <div className={styles.selectionBar}>
          <button
            type="button"
            className={styles.selectAllBtn}
            onClick={toggleSelectAll}
            aria-pressed={allFilteredSelected}
          >
            {allFilteredSelected ? <CheckSquare size={14} aria-hidden="true" /> : <Square size={14} aria-hidden="true" />}
            {t("selectAll")}
          </button>
          {selected.size > 0 && (
            <button type="button" className={styles.downloadSelectedBtn} onClick={downloadSelected}>
              <Download size={13} aria-hidden="true" /> {t("downloadSelected")} ({selected.size})
            </button>
          )}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className={styles.empty}>{t("emptyForFilter")}</div>
      ) : (
        <ul className={styles.list}>
          {filtered.map((file) => {
            const category = getFileCategory(file.content_type);
            const canPreview = PREVIEWABLE.has(category);
            const isSelected = selected.has(file.filename);
            return (
              // Keyed by filename, not array index: filenames are unique
              // within a job (unique_filename guarantees it) and stable across
              // filter changes, whereas an index key made React reuse the DOM
              // node of a *different* file when the filter changed, carrying
              // the previous row's checkbox state and <img> over with it.
              <li key={file.filename} className={styles.item}>
                <button
                  type="button"
                  className={styles.checkbox}
                  onClick={() => toggleSelect(file.filename)}
                  role="checkbox"
                  aria-checked={isSelected}
                  aria-label={`${t("a11ySelectFile")}: ${file.filename}`}
                >
                  {isSelected ? <CheckSquare size={16} aria-hidden="true" /> : <Square size={16} aria-hidden="true" />}
                </button>

                {file.thumbnail && (
                  <img src={file.thumbnail} alt="" className={styles.thumb} loading="lazy" />
                )}
                <span className={styles.icon} data-cat={category} aria-hidden="true">
                  {FILE_ICONS[category] ?? FILE_ICONS.other}
                </span>

                {/* A real <button> when it is interactive: the old clickable
                    <div> was unreachable by keyboard and announced nothing. */}
                {canPreview ? (
                  <button
                    type="button"
                    className={`${styles.info} ${styles.infoClickable}`}
                    onClick={() => setPreviewFile(file)}
                    aria-label={`${t("a11yPreviewFile")}: ${file.filename}`}
                  >
                    <span className={styles.filename}>{file.filename}</span>
                    <span className={styles.meta}>
                      {file.content_type} · {formatBytes(file.size_bytes)}
                      {file.converted_ext && ` · ${t("convertedTo")} ${file.converted_ext}`}
                    </span>
                  </button>
                ) : (
                  <div className={styles.info}>
                    <span className={styles.filename}>{file.filename}</span>
                    <span className={styles.meta}>
                      {file.content_type} · {formatBytes(file.size_bytes)}
                      {file.converted_ext && ` · ${t("convertedTo")} ${file.converted_ext}`}
                    </span>
                  </div>
                )}

                <a
                  href={getDownloadUrl(file.filename)}
                  download={file.filename}
                  className={styles.downloadBtn}
                  aria-label={`${t("a11yDownloadFile")}: ${file.filename}`}
                >
                  <Download size={14} aria-hidden="true" />
                </a>
              </li>
            );
          })}
        </ul>
      )}

      {previewFile && (
        <div className={styles.previewOverlay} onClick={closePreview}>
          <div
            className={styles.previewModal}
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={`${t("a11yPreviewDialog")}: ${previewFile.filename}`}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.previewHeader}>
              <span className={styles.previewTitle}>{previewFile.filename}</span>
              <button
                type="button"
                className={styles.previewClose}
                onClick={closePreview}
                aria-label={t("a11yClosePreview")}
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <div className={styles.previewBody}>
              {previewCategory === "image" && (
                <img src={getPreviewUrl(previewFile.filename)} alt={previewFile.filename} className={styles.previewImg} />
              )}
              {previewCategory === "video" && (
                <video src={getPreviewUrl(previewFile.filename)} controls autoPlay className={styles.previewMedia} />
              )}
              {previewCategory === "audio" && (
                <audio src={getPreviewUrl(previewFile.filename)} controls autoPlay className={styles.previewAudio} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
