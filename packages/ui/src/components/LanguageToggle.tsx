import React from "react";
import { useI18n } from "../i18n";
import styles from "./ThemeToggle.module.css";

export function LanguageToggle() {
  const { locale, setLocale } = useI18n();

  return (
    <button
      type="button"
      className={styles.btn}
      onClick={() => setLocale(locale === "pt-BR" ? "en-US" : "pt-BR")}
      // The label is deliberately in the language being switched *to*, and
      // carries that language's `lang` so a screen reader pronounces it right.
      aria-label={locale === "pt-BR" ? "Switch to English" : "Mudar para português"}
      lang={locale === "pt-BR" ? "en" : "pt-BR"}
      title={locale === "pt-BR" ? "Switch to English" : "Mudar para português"}
    >
      {locale === "pt-BR" ? "PT" : "EN"}
    </button>
  );
}
