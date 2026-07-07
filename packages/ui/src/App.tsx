import React, { useEffect, useRef } from "react";
import { ExtractionForm } from "./components/ExtractionForm";
import { ProgressPanel } from "./components/ProgressPanel";
import { FileList } from "./components/FileList";
import { JobHistory } from "./components/JobHistory";
import { ThemeToggle } from "./components/ThemeToggle";
import { LanguageToggle } from "./components/LanguageToggle";
import { useExtraction } from "./hooks/useExtraction";
import { useTheme } from "./hooks/useTheme";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useI18n } from "./i18n";
import { notify } from "./notify";
import styles from "./App.module.css";

export default function App() {
  const { phase, job, start, cancel, reset, downloadUrl, downloadAllUrl, previewUrl, loadJob, pause, resume } = useExtraction();
  const [theme, toggleTheme] = useTheme();
  const { t } = useI18n();

  // Fire exactly one notification per job completion/failure, even though
  // the WebSocket may deliver several "done"/"error" JobState updates.
  const notifiedJobId = useRef<string | null>(null);
  useEffect(() => {
    if (!job) return;
    if ((phase === "done" || phase === "error") && notifiedJobId.current !== job.job_id) {
      notifiedJobId.current = job.job_id;
      const title = phase === "done" ? t("jobDoneTitle") : t("jobErrorTitle");
      notify(title, job.url);
    }
  }, [phase, job, t]);

  const openOutputFolder = () => {
    const electronAPI = (window as any).electronAPI;
    if (electronAPI?.isElectron && job?.output_dir) {
      electronAPI.openFolder(job.output_dir);
    }
  };

  useKeyboardShortcuts({
    onNewJob: () => { if (phase !== "idle") reset(); },
    onCancel: () => { if (phase === "starting" || phase === "running") cancel(); },
    onOpenFolder: openOutputFolder,
  });

  return (
    <div className={styles.app}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerBar}>
          <div className={styles.logo}>
            <span className={styles.logoMark}>◈</span>
            <span className={styles.logoName}>PageCap</span>
          </div>
          <div className={styles.headerActions}>
            <JobHistory onSelect={loadJob} activeJobId={job?.job_id} />
            <LanguageToggle />
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
        </div>
        <p className={styles.tagline}>{t("tagline")}</p>
      </header>

      {/* Main */}
      <main className={styles.main}>
        <div className={styles.card}>
          {phase === "idle" && (
            <ExtractionForm onSubmit={start} disabled={false} />
          )}

          {(phase === "starting" || phase === "running") && job && (
            <>
              <ExtractionForm onSubmit={start} disabled={true} />
              <ProgressPanel job={job} phase={phase} onCancel={cancel} onPause={pause} onResume={resume} />
            </>
          )}

          {phase === "error" && job && (
            <>
              <ExtractionForm onSubmit={start} disabled={false} />
              <ProgressPanel job={job} phase={phase} />
              {job.files.length > 0 && (
                <FileList
                  files={job.files}
                  outputDir={job.output_dir}
                  getDownloadUrl={downloadUrl}
                  getPreviewUrl={previewUrl}
                  getDownloadAllUrl={downloadAllUrl}
                  onReset={reset}
                />
              )}
            </>
          )}

          {phase === "done" && job && (
            <>
              <ProgressPanel job={job} phase={phase} />
              <FileList
                files={job.files}
                outputDir={job.output_dir}
                getDownloadUrl={downloadUrl}
                getPreviewUrl={previewUrl}
                getDownloadAllUrl={downloadAllUrl}
                onReset={reset}
              />
            </>
          )}
        </div>
      </main>

      <footer className={styles.footer}>
        <span>PageCap v1.0</span>
        <span>·</span>
        <span>API: <code>http://127.0.0.1:8765</code></span>
        <span>·</span>
        <span>CLI: <code>python engine/cli.py --help</code></span>
      </footer>
    </div>
  );
}
