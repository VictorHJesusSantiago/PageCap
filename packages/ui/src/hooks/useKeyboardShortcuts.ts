import { useEffect } from "react";

export interface ShortcutHandlers {
  onNewJob?: () => void;      // Ctrl/Cmd+N
  onCancel?: () => void;      // Escape
  onOpenFolder?: () => void;  // Ctrl/Cmd+O
}

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || el.isContentEditable;
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;

      if (e.key === "Escape" && handlers.onCancel) {
        handlers.onCancel();
        return;
      }

      // Ctrl/Cmd+N and Ctrl/Cmd+O only fire outside text inputs, so typing a
      // URL or search text never accidentally triggers them.
      if (isTypingTarget(e.target)) return;

      if (mod && e.key.toLowerCase() === "n" && handlers.onNewJob) {
        e.preventDefault();
        handlers.onNewJob();
      } else if (mod && e.key.toLowerCase() === "o" && handlers.onOpenFolder) {
        e.preventDefault();
        handlers.onOpenFolder();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handlers.onNewJob, handlers.onCancel, handlers.onOpenFolder]);
}
