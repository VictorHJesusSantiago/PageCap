import React from "react";
import { JobState } from "@pagecap/core";
import { Loader2, CheckCircle2, XCircle, X } from "lucide-react";
import styles from "./ProgressPanel.module.css";

interface Props {
  job: JobState;
  phase: "starting" | "running" | "done" | "error";
  onCancel?: () => void;
}

// Maps job.status to a human label shown on top of phase
const STATUS_LABELS: Partial<Record<string, string>> = {
  waiting_captcha: "Aguardando CAPTCHA / 2FA",
};

export function ProgressPanel({ job, phase, onCancel }: Props) {
  const isActive = phase === "starting" || phase === "running";

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.statusIcon}>
          {isActive && <Loader2 size={18} className={styles.spin} />}
          {phase === "done" && <CheckCircle2 size={18} className={styles.done} />}
          {phase === "error" && <XCircle size={18} className={styles.error} />}
        </div>
        <div className={styles.statusText}>
          <span className={styles.statusLabel}>
            {STATUS_LABELS[job.status] ?? (
              phase === "starting" ? "Iniciando..." :
              phase === "running" ? "Extraindo" :
              phase === "done" ? "Concluído" :
              "Erro"
            )}
          </span>
          <span className={styles.url}>{job.url}</span>
        </div>
        {isActive && onCancel && (
          <button className={styles.cancelBtn} onClick={onCancel} title="Cancelar">
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

      {job.error && (
        <div className={styles.errorMsg}>
          {job.error}
        </div>
      )}

      {job.files.length > 0 && (
        <div className={styles.counter}>
          {job.files.length} arquivo{job.files.length !== 1 ? "s" : ""} encontrado{job.files.length !== 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
