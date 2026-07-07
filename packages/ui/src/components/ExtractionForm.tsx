import React, { useState } from "react";
import { ExtractionRequest, ContentType, AuthMethod, CookiesBrowser } from "@pagecap/core";
import { Globe, Lock, Cookie, Folder, ChevronDown, ChevronUp, Filter } from "lucide-react";
import { FilterRulesEditor } from "./FilterRulesEditor";
import styles from "./ExtractionForm.module.css";

interface Props {
  onSubmit: (req: ExtractionRequest) => void;
  disabled?: boolean;
}

const CONTENT_TYPES: { value: ContentType; label: string; icon: string }[] = [
  { value: "all", label: "Tudo", icon: "🌐" },
  { value: "page_pdf", label: "Página (PDF)", icon: "📄" },
  { value: "images", label: "Imagens", icon: "🖼️" },
  { value: "videos", label: "Vídeos", icon: "🎬" },
  { value: "audio", label: "Áudio", icon: "🎵" },
  { value: "documents", label: "Documentos", icon: "📁" },
];

const BROWSERS: CookiesBrowser[] = ["chrome", "firefox", "edge", "brave", "opera", "safari"];

export function ExtractionForm({ onSubmit, disabled }: Props) {
  const [url, setUrl] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<ContentType[]>(["all"]);
  const [authMethod, setAuthMethod] = useState<AuthMethod>("none");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [cookiesRaw, setCookiesRaw] = useState("");
  const [cookiesBrowser, setCookiesBrowser] = useState<CookiesBrowser>("chrome");
  const [outputDir, setOutputDir] = useState("");
  const [quality, setQuality] = useState<"best" | "worst">("best");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [manualCaptcha, setManualCaptcha] = useState(false);
  const [screenRecord, setScreenRecord] = useState(false);
  const [screenDuration, setScreenDuration] = useState(60);
  const [networkWait, setNetworkWait] = useState(12);
  const [isDragOver, setIsDragOver] = useState(false);
  const [targetExtensions, setTargetExtensions] = useState<string[]>([]);
  const [urlPattern, setUrlPattern] = useState("");
  const [minFileSizeBytes, setMinFileSizeBytes] = useState(0);
  const [zipOutput, setZipOutput] = useState(false);
  const [generateThumbnails, setGenerateThumbnails] = useState(false);

  const extractUrlFromDrop = (e: React.DragEvent): string | null => {
    const uriList = e.dataTransfer.getData("text/uri-list");
    const plain = e.dataTransfer.getData("text/plain");
    const candidate = (uriList || plain || "").split("\n")[0].trim();
    try {
      const parsed = new URL(candidate);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") return candidate;
    } catch {
      /* not a valid absolute URL — ignore the drop */
    }
    return null;
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragOver(true);
  };

  const handleDragLeave = () => setIsDragOver(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (disabled) return;
    const dropped = extractUrlFromDrop(e);
    if (dropped) setUrl(dropped);
  };

  const toggleType = (ct: ContentType) => {
    if (ct === "all") {
      setSelectedTypes(["all"]);
      return;
    }
    setSelectedTypes((prev) => {
      const without = prev.filter((t) => t !== "all");
      return without.includes(ct) ? without.filter((t) => t !== ct) : [...without, ct];
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    const req: ExtractionRequest = {
      url: url.trim(),
      content_types: selectedTypes.length ? selectedTypes : ["all"],
      quality,
      output_dir: outputDir || undefined,
      network_wait: networkWait,
      screen_record: screenRecord,
      screen_record_duration: screenDuration,
      auth: { method: authMethod, manual_captcha: manualCaptcha },
      target_extensions: targetExtensions.length ? targetExtensions : undefined,
      url_pattern: urlPattern.trim() || undefined,
      min_file_size_bytes: minFileSizeBytes || undefined,
      zip_output: zipOutput,
      generate_thumbnails: generateThumbnails,
    };

    if (authMethod === "credentials") {
      req.auth = { method: "credentials", username, password };
    } else if (authMethod === "cookies") {
      req.auth = { method: "cookies", cookies_raw: cookiesRaw };
    } else if (authMethod === "cookies_browser") {
      req.auth = { method: "cookies_browser", cookies_browser: cookiesBrowser };
    }

    onSubmit(req);
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      {/* URL */}
      <div
        className={`${styles.urlRow} ${isDragOver ? styles.urlRowDragOver : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <Globe size={16} className={styles.urlIcon} />
        <input
          type="url"
          className={styles.urlInput}
          placeholder="https://exemplo.com  (ou arraste um link aqui)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          disabled={disabled}
        />
        <button type="submit" className={styles.extractBtn} disabled={disabled || !url.trim()}>
          {disabled ? "Extraindo..." : "Extrair"}
        </button>
      </div>

      {/* Content types */}
      <div className={styles.section}>
        <label className={styles.sectionLabel}>O que extrair</label>
        <div className={styles.typeGrid}>
          {CONTENT_TYPES.map((ct) => (
            <button
              key={ct.value}
              type="button"
              className={`${styles.typeBtn} ${selectedTypes.includes(ct.value) ? styles.typeBtnActive : ""}`}
              onClick={() => toggleType(ct.value)}
              disabled={disabled}
            >
              <span>{ct.icon}</span>
              <span>{ct.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Auth */}
      <div className={styles.section}>
        <label className={styles.sectionLabel}>
          <Lock size={13} /> Autenticação
        </label>
        <div className={styles.authTabs}>
          {(["none", "credentials", "cookies", "cookies_browser"] as AuthMethod[]).map((m) => (
            <button
              key={m}
              type="button"
              className={`${styles.authTab} ${authMethod === m ? styles.authTabActive : ""}`}
              onClick={() => setAuthMethod(m)}
              disabled={disabled}
            >
              {m === "none" && "Nenhuma"}
              {m === "credentials" && "Login/Senha"}
              {m === "cookies" && "Cookies (texto)"}
              {m === "cookies_browser" && "Cookies do Browser"}
            </button>
          ))}
        </div>

        {authMethod === "credentials" && (
          <div className={styles.authFields}>
            <input
              type="text"
              className={styles.input}
              placeholder="Usuário ou e-mail"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={disabled}
            />
            <input
              type="password"
              className={styles.input}
              placeholder="Senha"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={disabled}
            />
          </div>
        )}

        {authMethod === "cookies" && (
          <div className={styles.authFields}>
            <textarea
              className={styles.textarea}
              placeholder={"Cole aqui seus cookies:\n  • Formato header: key=val; key2=val2\n  • Formato Netscape: arquivo exportado"}
              value={cookiesRaw}
              onChange={(e) => setCookiesRaw(e.target.value)}
              rows={4}
              disabled={disabled}
            />
          </div>
        )}

        {authMethod === "cookies_browser" && (
          <div className={styles.authFields}>
            <div className={styles.row}>
              <Cookie size={14} className={styles.inputIcon} />
              <select
                className={styles.select}
                value={cookiesBrowser}
                onChange={(e) => setCookiesBrowser(e.target.value as CookiesBrowser)}
                disabled={disabled}
              >
                {BROWSERS.map((b) => (
                  <option key={b} value={b}>
                    {b.charAt(0).toUpperCase() + b.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <p className={styles.hint}>
              O PageCap vai ler os cookies da sessão ativa do {cookiesBrowser} para este site.
              O browser deve estar instalado na máquina.
            </p>
          </div>
        )}
      </div>

      {/* Advanced */}
      <button
        type="button"
        className={styles.advancedToggle}
        onClick={() => setAdvancedOpen((p) => !p)}
      >
        {advancedOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        Opções avançadas
      </button>

      {advancedOpen && (
        <div className={styles.advancedPanel}>
          <div className={styles.advancedRow}>
            <label className={styles.advancedLabel}>
              <Folder size={13} /> Pasta de saída
            </label>
            <input
              type="text"
              className={styles.input}
              placeholder="./downloads  (padrão)"
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
              disabled={disabled}
            />
          </div>
          <div className={styles.advancedRow}>
            <label className={styles.advancedLabel}>Qualidade de vídeo</label>
            <div className={styles.radioGroup}>
              <label>
                <input type="radio" value="best" checked={quality === "best"} onChange={() => setQuality("best")} disabled={disabled} />
                Melhor
              </label>
              <label>
                <input type="radio" value="worst" checked={quality === "worst"} onChange={() => setQuality("worst")} disabled={disabled} />
                Menor arquivo
              </label>
            </div>
          </div>

          <div className={styles.advancedRow}>
            <label className={styles.advancedLabel}>Aguardar mídia (interceptação de rede)</label>
            <div className={styles.radioGroup}>
              <input
                type="number" min={3} max={60} className={styles.inputSmall}
                value={networkWait} onChange={(e) => setNetworkWait(Number(e.target.value))}
                disabled={disabled}
              />
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>segundos</span>
            </div>
          </div>

          <div className={styles.advancedRow}>
            <label className={styles.checkLabel}>
              <input type="checkbox" checked={manualCaptcha} onChange={(e) => setManualCaptcha(e.target.checked)} disabled={disabled} />
              Abrir browser visível para CAPTCHA / 2FA manual
            </label>
            <p className={styles.hint}>Se o site tiver CAPTCHA ou autenticação em dois fatores, o browser abrirá na tela para você resolver. A extração continua automaticamente depois.</p>
          </div>

          <div className={styles.advancedRow}>
            <label className={styles.checkLabel}>
              <input type="checkbox" checked={screenRecord} onChange={(e) => setScreenRecord(e.target.checked)} disabled={disabled} />
              Gravar tela como fallback (requer ffmpeg)
            </label>
            {screenRecord && (
              <div className={styles.radioGroup} style={{ marginTop: 6 }}>
                <input
                  type="number" min={10} max={3600} className={styles.inputSmall}
                  value={screenDuration} onChange={(e) => setScreenDuration(Number(e.target.value))}
                  disabled={disabled}
                />
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>segundos de gravação</span>
              </div>
            )}
            <p className={styles.hint}>Captura o que é exibido na tela (funciona com players que não podem ser interceptados na rede).</p>
          </div>

          <div className={styles.advancedRow}>
            <label className={styles.advancedLabel}>
              <Filter size={13} /> Regras de filtro
            </label>
            <FilterRulesEditor
              extensions={targetExtensions}
              onExtensionsChange={setTargetExtensions}
              urlPattern={urlPattern}
              onUrlPatternChange={setUrlPattern}
              minSizeBytes={minFileSizeBytes}
              onMinSizeBytesChange={setMinFileSizeBytes}
              disabled={disabled}
            />
          </div>

          <div className={styles.advancedRow}>
            <label className={styles.checkLabel}>
              <input type="checkbox" checked={zipOutput} onChange={(e) => setZipOutput(e.target.checked)} disabled={disabled} />
              Compactar tudo em .zip ao concluir
            </label>
          </div>

          <div className={styles.advancedRow}>
            <label className={styles.checkLabel}>
              <input type="checkbox" checked={generateThumbnails} onChange={(e) => setGenerateThumbnails(e.target.checked)} disabled={disabled} />
              Gerar miniaturas de imagens/vídeos
            </label>
          </div>
        </div>
      )}
    </form>
  );
}
