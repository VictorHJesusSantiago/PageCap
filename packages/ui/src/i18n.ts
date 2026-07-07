import { createContext, useContext, useState, useCallback, createElement, ReactNode } from "react";

export type Locale = "pt-BR" | "en-US";

const STORAGE_KEY = "pagecap-locale";

// Covers the primary navigation/status surface (header, form section labels,
// progress states, file list chrome). Deep per-field microcopy inside every
// advanced-option tooltip is not exhaustively translated — this is a
// functional language switch for the core flow, not a full localization pass.
const DICTIONARIES: Record<Locale, Record<string, string>> = {
  "pt-BR": {
    tagline: "Extrai qualquer conteúdo de qualquer página web",
    history: "Histórico de jobs",
    newExtraction: "Nova extração",
    extract: "Extrair",
    extracting: "Extraindo...",
    whatToExtract: "O que extrair",
    authentication: "Autenticação",
    advancedOptions: "Opções avançadas",
    starting: "Iniciando...",
    running: "Extraindo",
    done: "Concluído",
    error: "Erro",
    paused: "Pausado",
    cancel: "Cancelar",
    pause: "Pausar",
    resume: "Retomar",
    filesFound: "arquivo(s) encontrado(s)",
    downloadAll: "Baixar tudo",
    selectAll: "Selecionar todos",
    downloadSelected: "Baixar selecionados",
    jobDoneTitle: "Extração concluída",
    jobErrorTitle: "Extração falhou",
  },
  "en-US": {
    tagline: "Extract any content from any web page",
    history: "Job history",
    newExtraction: "New extraction",
    extract: "Extract",
    extracting: "Extracting...",
    whatToExtract: "What to extract",
    authentication: "Authentication",
    advancedOptions: "Advanced options",
    starting: "Starting...",
    running: "Extracting",
    done: "Done",
    error: "Error",
    paused: "Paused",
    cancel: "Cancel",
    pause: "Pause",
    resume: "Resume",
    filesFound: "file(s) found",
    downloadAll: "Download all",
    selectAll: "Select all",
    downloadSelected: "Download selected",
    jobDoneTitle: "Extraction complete",
    jobErrorTitle: "Extraction failed",
  },
};

function getInitialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "en-US" || stored === "pt-BR" ? stored : "pt-BR";
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem(STORAGE_KEY, l);
  }, []);

  const t = useCallback((key: string) => DICTIONARIES[locale][key] ?? key, [locale]);

  return createElement(I18nContext.Provider, { value: { locale, setLocale, t } }, children);
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
