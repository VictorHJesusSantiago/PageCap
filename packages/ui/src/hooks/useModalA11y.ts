import { useEffect, useRef } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  'video[controls]',
  'audio[controls]',
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/**
 * WCAG 2.1 keyboard requirements for a modal dialog, in one place:
 *
 *  - Escape closes it (2.1.2 No Keyboard Trap needs an escape route).
 *  - Tab cycles *within* the dialog instead of walking into the page behind it,
 *    which a screen-reader or keyboard user cannot see is inert.
 *  - Focus moves into the dialog on open and returns to whatever opened it on
 *    close (3.2.1 On Focus), so the reading position is not lost.
 *
 * Returns the ref to attach to the dialog container.
 */
export function useModalA11y(isOpen: boolean, onClose: () => void) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const container = containerRef.current;

    // Visibility filter. Deliberately NOT `offsetParent !== null`: that returns
    // null for every `position: fixed` element, which is exactly what a modal
    // overlay is, so it would have filtered out the dialog's own contents.
    // checkVisibility() is the correct API; where it is unavailable (older
    // engines, jsdom) fall back to the attribute checks alone.
    const isVisible = (el: HTMLElement) => {
      if (el.hasAttribute("hidden") || el.getAttribute("aria-hidden") === "true") return false;
      return typeof el.checkVisibility === "function" ? el.checkVisibility() : true;
    };

    // Focus the first interactive element, falling back to the container so
    // the dialog itself is announced when it holds nothing focusable.
    const focusables = () =>
      Array.from(container?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(isVisible);
    (focusables()[0] ?? container)?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;

      const items = focusables();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;

      if (e.shiftKey && (active === first || active === container)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      previouslyFocused.current?.focus?.();
    };
  }, [isOpen, onClose]);

  return containerRef;
}
