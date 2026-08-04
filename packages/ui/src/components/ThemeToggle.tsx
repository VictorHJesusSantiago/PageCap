import React from "react";
import { Sun, Moon } from "lucide-react";
import { Theme } from "../hooks/useTheme";
import { useI18n } from "../i18n";
import styles from "./ThemeToggle.module.css";

interface Props {
  theme: Theme;
  onToggle: () => void;
}

export function ThemeToggle({ theme, onToggle }: Props) {
  const { t } = useI18n();
  const label = t("a11yToggleTheme");
  return (

    <button
      type="button"
      className={styles.btn}
      onClick={onToggle}
      aria-label={label}
      aria-pressed={theme === "dark"}
      title={label}
    >
      {theme === "dark" ? <Sun size={14} aria-hidden="true" /> : <Moon size={14} aria-hidden="true" />}
    </button>
  );
}
