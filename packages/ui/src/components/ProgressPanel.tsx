import React from "react";
import { JobState } from "@pagecap/core";
import { Loader2, CheckCircle2, XCircle, X, Check, Pause, Play, AlertTriangle } from "lucide-react";
import { useI18n } from "../i18n";
import styles from "./ProgressPanel.module.css";

interface Props {
  job: JobState;
  phase: "starting" | "running" | "done" | "error";
  onCancel?: () => void;
  onPause?: () => void;
  onResume?: () => void;
}

function formatBytes(b?: number | null): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(2)} MB`;
}

export function ProgressPanel({ job, phase, onCancel, onPause, onResume }: Props) {
  const { t } = useI18n();
  const isActive = phase === "starting" || phase === "running";
  const isPaused = job.status === "paused";

  const statusLabel =
    job.status === "waiting_captcha" ? "Aguardando CAPTCHA / 2FA" :
    isPaused ? t("paused") :
    phase === "starting" ? t("starting") :
    phase === "running" ? t("running") :
    phase === "done" ? t("done") :
    t("error");

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.statusIcon}>
          {isPaused && <Pause size={18} className={styles.paused} />}
          {isActive && !isPaused && <Loader2 size={18} className={styles.spin} />}
          {phase === "done" && <CheckCircle2 size={18} className={styles.done} />}
          {phase === "error" && <XCircle size={18} className={styles.error} />}
        </div>
        <div className={styles.statusText}>
          <span className={styles.statusLabel}>{statusLabel}</span>
          <span className={styles.url}>{job.url}</span>
        </div>
        {isActive && job.status === "running" && onPause && (
          <button className={styles.cancelBtn} onClick={onPause} title={t("pause")}>
            <Pause size={14} />
          </button>
        )}
        {isActive && isPaused && onResume && (
          <button className={styles.cancelBtn} onClick={onResume} title={t("resume")}>
            <Play size={14} />
          </button>
        )}
        {isActive && onCancel && (
          <button className={styles.cancelBtn} onClick={onCancel} title={t("cancel")}>
            <X size={14} />
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div className={styles.progressTrack}>
        <div
          className={`${styles.progressBar} ${phase === "done" ? styles.progressDone : ""}`}
          style={{ width: `${job.progress}%` }}
        />
      </div>

      <div className={styles.meta}>
        <span className={styles.message}>{job.message}</span>
        <span className={styles.pct}>{job.progress}%</span>
      </div>

      {/* Byte-level progress of whichever file is downloading right now */}
      {isActive && job.current_file && (
        <div className={styles.currentFile}>
          <span className={styles.currentFileName}>{job.current_file.filename}</span>
          <div className={styles.currentFileTrack}>
            <div
              className={styles.currentFileBar}
              style={{
                width: job.current_file.bytes_total
                  ? `${Math.min(100, (job.current_file.bytes_done / job.current_file.bytes_total) * 100)}%`
                  : "100%",
              }}
            />
          </div>
          <span className={styles.currentFileBytes}>
            {formatBytes(job.current_file.bytes_done)}
            {job.current_file.bytes_total ? ` / ${formatBytes(job.current_file.bytes_total)}` : ""}
          </span>
        </div>
      )}

      {job.paywall_warning && (
        <div className={styles.warningMsg}>
          <AlertTriangle size={14} />
          {job.paywall_warning}
        </div>
      )}

      {job.error && (
        <div className={styles.errorMsg}>
          {job.error}
        </div>
      )}

      {job.files.length > 0 && (
        <div className={styles.counter}>
          {job.files.length} {t("filesFound")}
        </div>
      )}

      {job.diff && (
        <div className={styles.diff}>
          <span className={styles.diffAdded}>+{job.diff.added.length}</span>
          <span className={styles.diffRemoved}>-{job.diff.removed.length}</span>
          <span className={styles.diffChanged}>~{job.diff.changed.length}</span>
          <span className={styles.diffLabel}>vs. job anterior</span>
        </div>
      )}

      {/* Per-file feed: shows each asset the instant it lands, most recent
          first, so progress reads as concrete files rather than only a
          percentage. */}
      {isActive && job.files.length > 0 && (
        <div className={styles.fileFeed}>
          {[...job.files].reverse().slice(0, 8).map((f, i) => (
            <div key={`${f.filename}-${i}`} className={styles.fileFeedItem}>
              <Check size={12} className={styles.fileFeedCheck} />
              <span className={styles.fileFeedName}>{f.filename}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
