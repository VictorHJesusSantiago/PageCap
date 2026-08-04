import { createContext, useContext, useState, useCallback, useEffect, createElement, ReactNode } from "react";

export type Locale = "pt-BR" | "en-US";

const STORAGE_KEY = "pagecap-locale";

export const DICTIONARIES: Record<Locale, Record<string, string>> = {
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

    filesExtracted: "arquivo(s) extraído(s)",
    totalSize: "total",
    filterAll: "Todos",
    filterPdf: "PDF",
    filterImage: "Imagens",
    filterVideo: "Vídeos",
    filterAudio: "Áudio",
    filterDocument: "Documentos",
    emptyForFilter: "Nenhum arquivo deste tipo.",
    convertedTo: "convertido para",
    outputFolder: "Pasta de saída",

    a11ySelectFile: "Selecionar arquivo",
    a11yDownloadFile: "Baixar arquivo",
    a11yPreviewFile: "Pré-visualizar arquivo",
    a11yClosePreview: "Fechar pré-visualização",
    a11yRefreshHistory: "Atualizar histórico",
    a11yToggleTheme: "Alternar tema claro/escuro",
    a11yPreviewDialog: "Pré-visualização do arquivo",
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

    filesExtracted: "file(s) extracted",
    totalSize: "total",
    filterAll: "All",
    filterPdf: "PDF",
    filterImage: "Images",
    filterVideo: "Videos",
    filterAudio: "Audio",
    filterDocument: "Documents",
    emptyForFilter: "No files of this type.",
    convertedTo: "converted to",
    outputFolder: "Output folder",

    a11ySelectFile: "Select file",
    a11yDownloadFile: "Download file",
    a11yPreviewFile: "Preview file",
    a11yClosePreview: "Close preview",
    a11yRefreshHistory: "Refresh history",
    a11yToggleTheme: "Toggle light/dark theme",
    a11yPreviewDialog: "File preview",
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

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

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
