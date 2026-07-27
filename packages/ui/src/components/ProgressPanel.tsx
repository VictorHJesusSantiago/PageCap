import React from "react";
import { JobState } from "@pagecap/core";
import { Loader2, CheckCircle2, XCircle, X, Check, Pause, Play, AlertTriangle } from "lucide-react";
import { formatBytes } from "../format";
import { useI18n } from "../i18n";
import styles from "./ProgressPanel.module.css";

interface Props {
  job: JobState;
  phase: "starting" | "running" | "done" | "error";
  onCancel?: () => void;
  onPause?: () => void;
  onResume?: () => void;
}

/** In a progress readout a falsy size means "nothing transferred yet", not
 * "unknown", so the shared helper's default fallback is overridden. */
const formatProgressBytes = (b?: number | null) => formatBytes(b, "0 B");

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
          <button type="button" className={styles.cancelBtn} onClick={onPause} aria-label={t("pause")} title={t("pause")}>
            <Pause size={14} aria-hidden="true" />
          </button>
        )}
        {isActive && isPaused && onResume && (
          <button type="button" className={styles.cancelBtn} onClick={onResume} aria-label={t("resume")} title={t("resume")}>
            <Play size={14} aria-hidden="true" />
          </button>
        )}
        {isActive && onCancel && (
          <button type="button" className={styles.cancelBtn} onClick={onCancel} aria-label={t("cancel")} title={t("cancel")}>
            <X size={14} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Progress bar. role=progressbar + aria-valuenow is what makes the
          percentage perceivable to a screen reader — a styled div width is not. */}
      <div
        className={styles.progressTrack}
        role="progressbar"
        aria-valuenow={job.progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={statusLabel}
      >
        <div
          className={`${styles.progressBar} ${phase === "done" ? styles.progressDone : ""}`}
          style={{ width: `${job.progress}%` }}
        />
      </div>

      {/* aria-live=polite announces each new stage message without interrupting
          whatever the user is currently reading. */}
      <div className={styles.meta} aria-live="polite" aria-atomic="true">
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
            {formatProgressBytes(job.current_file.bytes_done)}
            {job.current_file.bytes_total ? ` / ${formatProgressBytes(job.current_file.bytes_total)}` : ""}
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
