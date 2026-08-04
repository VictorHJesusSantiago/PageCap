import { useEffect } from "react";

export interface ShortcutHandlers {
  onNewJob?: () => void;
  onCancel?: () => void;
  onOpenFolder?: () => void;
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
