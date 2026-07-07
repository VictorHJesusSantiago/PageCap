import React from "react";
import { Sun, Moon } from "lucide-react";
import { Theme } from "../hooks/useTheme";
import styles from "./ThemeToggle.module.css";

interface Props {
  theme: Theme;
  onToggle: () => void;
}

export function ThemeToggle({ theme, onToggle }: Props) {
  return (
    <button
      type="button"
      className={styles.btn}
      onClick={onToggle}
      title={theme === "dark" ? "Mudar para tema claro" : "Mudar para tema escuro"}
    >
      {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  );
}
