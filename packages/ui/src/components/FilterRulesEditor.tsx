import React, { useState } from "react";
import { X, Plus } from "lucide-react";
import styles from "./FilterRulesEditor.module.css";

interface Props {
  extensions: string[];
  onExtensionsChange: (exts: string[]) => void;
  urlPattern: string;
  onUrlPatternChange: (pattern: string) => void;
  minSizeBytes: number;
  onMinSizeBytesChange: (bytes: number) => void;
  disabled?: boolean;
}

/** Visual rule builder for what to include/exclude from an extraction:
 * extension chips (added one at a time), a regex the asset URL must match,
 * and a minimum file size — all map directly to backend ExtractionRequest
 * fields (target_extensions, url_pattern, min_file_size_bytes). */
export function FilterRulesEditor({
  extensions, onExtensionsChange,
  urlPattern, onUrlPatternChange,
  minSizeBytes, onMinSizeBytesChange,
  disabled,
}: Props) {
  const [draft, setDraft] = useState("");

  const addExtension = () => {
    let ext = draft.trim().toLowerCase();
    if (!ext) return;
    if (!ext.startsWith(".")) ext = `.${ext}`;
    if (!extensions.includes(ext)) onExtensionsChange([...extensions, ext]);
    setDraft("");
  };

  const removeExtension = (ext: string) => {
    onExtensionsChange(extensions.filter((e) => e !== ext));
  };

  return (
    <div className={styles.container}>
      <div className={styles.field}>
        <label className={styles.label}>Extensões específicas (vazio = usar categorias acima)</label>
        <div className={styles.chipRow}>
          {extensions.map((ext) => (
            <span key={ext} className={styles.chip}>
              {ext}
              <button
                type="button"
                onClick={() => removeExtension(ext)}
                disabled={disabled}
                aria-label={`Remover ${ext}`}
              >
                <X size={11} />
              </button>
            </span>
          ))}
          <div className={styles.chipInput}>
            <input
              type="text"
              placeholder=".pdf, .mp3..."
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addExtension();
                }
              }}
              disabled={disabled}
            />
            <button type="button" onClick={addExtension} disabled={disabled || !draft.trim()}>
              <Plus size={12} />
            </button>
          </div>
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Padrão de URL (regex)</label>
        <input
          type="text"
          className={styles.textInput}
          placeholder="ex.: /uploads/.*\.jpg$"
          value={urlPattern}
          onChange={(e) => onUrlPatternChange(e.target.value)}
          disabled={disabled}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Tamanho mínimo do arquivo</label>
        <div className={styles.sizeRow}>
          <input
            type="number"
            min={0}
            className={styles.sizeInput}
            value={Math.round(minSizeBytes / 1024)}
            onChange={(e) => onMinSizeBytesChange(Math.max(0, Number(e.target.value)) * 1024)}
            disabled={disabled}
          />
          <span>KB</span>
        </div>
      </div>
    </div>
  );
}
