import React, { useCallback, useEffect, useState } from "react";
import { JobState } from "@pagecap/core";
import { History, RefreshCw, CheckCircle2, XCircle, Loader2, Ban } from "lucide-react";
import { client } from "../apiClient";
import styles from "./JobHistory.module.css";

interface Props {
  onSelect: (jobId: string) => void;
  activeJobId?: string | null;
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  done: <CheckCircle2 size={14} className={styles.iconDone} />,
  error: <XCircle size={14} className={styles.iconError} />,
  cancelled: <Ban size={14} className={styles.iconCancelled} />,
  running: <Loader2 size={14} className={styles.iconRunning} />,
  queued: <Loader2 size={14} className={styles.iconRunning} />,
  waiting_captcha: <Loader2 size={14} className={styles.iconRunning} />,
};

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function JobHistory({ onSelect, activeJobId }: Props) {
  const [jobs, setJobs] = useState<JobState[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await client.listJobs();
      setJobs(list);
    } catch {
      // API offline — leave the list as-is rather than clearing it.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  return (
    <div className={styles.container}>
      <button className={styles.toggle} onClick={() => setOpen((o) => !o)} type="button">
        <History size={14} />
        Histórico de jobs
        {jobs.length > 0 && <span className={styles.count}>{jobs.length}</span>}
      </button>

      {open && (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>{jobs.length} job{jobs.length !== 1 ? "s" : ""}</span>
            <button className={styles.refreshBtn} onClick={refresh} disabled={loading} type="button">
              <RefreshCw size={13} className={loading ? styles.spin : ""} />
            </button>
          </div>

          {jobs.length === 0 ? (
            <div className={styles.empty}>Nenhum job ainda.</div>
          ) : (
            <div className={styles.list}>
              {jobs.map((j) => (
                <button
                  key={j.job_id}
                  type="button"
                  className={`${styles.item} ${j.job_id === activeJobId ? styles.itemActive : ""}`}
                  onClick={() => { onSelect(j.job_id); setOpen(false); }}
                >
                  {STATUS_ICON[j.status] ?? STATUS_ICON.queued}
                  <div className={styles.itemInfo}>
                    <span className={styles.itemUrl} title={j.url}>{j.url}</span>
                    <span className={styles.itemMeta}>
                      {formatDate(j.created_at)} · {j.files.length} arquivo{j.files.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
