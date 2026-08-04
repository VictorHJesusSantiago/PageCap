import React, { useId, useState } from "react";
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

const BYTES_PER_KB = 1024;

export function FilterRulesEditor({
  extensions, onExtensionsChange,
  urlPattern, onUrlPatternChange,
  minSizeBytes, onMinSizeBytesChange,
  disabled,
}: Props) {
  const [draft, setDraft] = useState("");

  const baseId = useId();
  const extId = `${baseId}-ext`;
  const patternId = `${baseId}-pattern`;
  const sizeId = `${baseId}-size`;

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
        <label className={styles.label} htmlFor={extId}>
          Extensões específicas (vazio = usar categorias acima)
        </label>
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
                <X size={11} aria-hidden="true" />
              </button>
            </span>
          ))}
          <div className={styles.chipInput}>
            <input
              id={extId}
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
            <button
              type="button"
              onClick={addExtension}
              disabled={disabled || !draft.trim()}
              aria-label="Adicionar extensão"
            >
              <Plus size={12} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor={patternId}>
          Padrão de URL (regex)
        </label>
        <input
          id={patternId}
          type="text"
          className={styles.textInput}
          placeholder="ex.: /uploads/.*\.jpg$"
          value={urlPattern}
          onChange={(e) => onUrlPatternChange(e.target.value)}
          disabled={disabled}
          spellCheck={false}
          autoComplete="off"
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor={sizeId}>
          Tamanho mínimo do arquivo
        </label>
        <div className={styles.sizeRow}>
          <input
            id={sizeId}
            type="number"
            min={0}
            className={styles.sizeInput}
            value={Math.round(minSizeBytes / BYTES_PER_KB)}
            onChange={(e) =>
              onMinSizeBytesChange(Math.max(0, Number(e.target.value)) * BYTES_PER_KB)
            }
            disabled={disabled}
          />
          <span aria-hidden="true">KB</span>
        </div>
      </div>
    </div>
  );
}
