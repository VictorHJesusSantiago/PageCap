import React from "react";
import { ExtractionForm } from "./components/ExtractionForm";
import { ProgressPanel } from "./components/ProgressPanel";
import { FileList } from "./components/FileList";
import { useExtraction } from "./hooks/useExtraction";
import styles from "./App.module.css";

export default function App() {
  const { phase, job, start, cancel, reset, downloadUrl } = useExtraction();

  return (
    <div className={styles.app}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.logo}>
          <span className={styles.logoMark}>◈</span>
          <span className={styles.logoName}>PageCap</span>
        </div>
        <p className={styles.tagline}>Extrai qualquer conteúdo de qualquer página web</p>
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
              <ProgressPanel job={job} phase={phase} onCancel={cancel} />
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
