import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, renderHook, screen, userEvent } from "../test/render";
import { useTheme } from "./useTheme";
import { useKeyboardShortcuts } from "./useKeyboardShortcuts";
import { notify } from "../notify";
import { DICTIONARIES, I18nProvider, useI18n } from "../i18n";

describe("useTheme", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-theme");
  });

  it("defaults to dark when nothing is stored and the OS prefers dark", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("dark");
  });

  it("honours a stored preference", () => {
    localStorage.setItem("pagecap-theme", "light");
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("light");
  });

  it("follows prefers-color-scheme: light when nothing is stored", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList);
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("light");
  });

  it("reflects the theme onto <html data-theme> so CSS variables switch", () => {
    const { result } = renderHook(() => useTheme());
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    act(() => result.current[1]());
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("persists the toggle", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current[1]());
    expect(localStorage.getItem("pagecap-theme")).toBe("light");
  });

  it("toggles back and forth", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current[1]());
    act(() => result.current[1]());
    expect(result.current[0]).toBe("dark");
  });
});

describe("useKeyboardShortcuts", () => {
  function Harness(props: Parameters<typeof useKeyboardShortcuts>[0]) {
    useKeyboardShortcuts(props);
    return (
      <div>
        <input aria-label="url" />
        <textarea aria-label="notes" />
      </div>
    );
  }

  it("fires onCancel on Escape", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<Harness onCancel={onCancel} />);
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("fires onNewJob on Ctrl+N", async () => {
    const onNewJob = vi.fn();
    const user = userEvent.setup();
    render(<Harness onNewJob={onNewJob} />);
    await user.keyboard("{Control>}n{/Control}");
    expect(onNewJob).toHaveBeenCalledOnce();
  });

  it("fires onOpenFolder on Ctrl+O", async () => {
    const onOpenFolder = vi.fn();
    const user = userEvent.setup();
    render(<Harness onOpenFolder={onOpenFolder} />);
    await user.keyboard("{Control>}o{/Control}");
    expect(onOpenFolder).toHaveBeenCalledOnce();
  });

  it("accepts Meta as the modifier for macOS", async () => {
    const onNewJob = vi.fn();
    const user = userEvent.setup();
    render(<Harness onNewJob={onNewJob} />);
    await user.keyboard("{Meta>}n{/Meta}");
    expect(onNewJob).toHaveBeenCalledOnce();
  });

  it("does not hijack Ctrl+N while the user is typing in an input", async () => {
    const onNewJob = vi.fn();
    const user = userEvent.setup();
    render(<Harness onNewJob={onNewJob} />);
    await user.click(screen.getByLabelText("url"));
    await user.keyboard("{Control>}n{/Control}");
    expect(onNewJob).not.toHaveBeenCalled();
  });

  it("does not hijack Ctrl+O inside a textarea", async () => {
    const onOpenFolder = vi.fn();
    const user = userEvent.setup();
    render(<Harness onOpenFolder={onOpenFolder} />);
    await user.click(screen.getByLabelText("notes"));
    await user.keyboard("{Control>}o{/Control}");
    expect(onOpenFolder).not.toHaveBeenCalled();
  });

  it("still allows Escape while typing, so a job can always be cancelled", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<Harness onCancel={onCancel} />);
    await user.click(screen.getByLabelText("url"));
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("ignores an unbound key", async () => {
    const onNewJob = vi.fn();
    const user = userEvent.setup();
    render(<Harness onNewJob={onNewJob} />);
    await user.keyboard("{Control>}q{/Control}");
    expect(onNewJob).not.toHaveBeenCalled();
  });

  it("removes its listener on unmount", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    const { unmount } = render(<Harness onCancel={onCancel} />);
    unmount();
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });
});

describe("notify", () => {
  it("routes through the Electron bridge when present", async () => {
    const electronNotify = vi.fn().mockResolvedValue(undefined);
    (window as any).electronAPI = { isElectron: true, notify: electronNotify };
    try {
      await notify("title", "body");
      expect(electronNotify).toHaveBeenCalledWith("title", "body");
    } finally {
      delete (window as any).electronAPI;
    }
  });

  it("uses the browser Notification API when permission is already granted", async () => {
    const ctor = vi.fn();
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "granted", requestPermission: vi.fn() }));
    await notify("t", "b");
    expect(ctor).toHaveBeenCalledWith("t", { body: "b" });
    vi.unstubAllGlobals();
  });

  it("requests permission once when undecided, then notifies", async () => {
    const ctor = vi.fn();
    const requestPermission = vi.fn().mockResolvedValue("granted");
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "default", requestPermission }));
    await notify("t", "b");
    expect(requestPermission).toHaveBeenCalledOnce();
    expect(ctor).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it("stays silent when the user denied notifications", async () => {
    const ctor = vi.fn();
    const requestPermission = vi.fn();
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "denied", requestPermission }));
    await notify("t", "b");
    expect(requestPermission).not.toHaveBeenCalled();
    expect(ctor).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("stays silent when permission is requested and refused", async () => {
    const ctor = vi.fn();
    vi.stubGlobal(
      "Notification",
      Object.assign(ctor, { permission: "default", requestPermission: vi.fn().mockResolvedValue("denied") }),
    );
    await notify("t", "b");
    expect(ctor).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe("i18n", () => {
  function Probe() {
    const { t, locale, setLocale } = useI18n();
    return (
      <div>
        <span data-testid="locale">{locale}</span>
        <span data-testid="tagline">{t("tagline")}</span>
        <span data-testid="missing">{t("no-such-key")}</span>
        <button type="button" onClick={() => setLocale("en-US")}>
          en
        </button>
      </div>
    );
  }

  it("defaults to pt-BR", () => {
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR");
  });

  it("switches language, persists it, and updates <html lang>", async () => {
    const user = userEvent.setup();
    render(<I18nProvider><Probe /></I18nProvider>);
    await user.click(screen.getByRole("button", { name: "en" }));

    expect(screen.getByTestId("locale")).toHaveTextContent("en-US");
    expect(screen.getByTestId("tagline")).toHaveTextContent("Extract any content");
    expect(localStorage.getItem("pagecap-locale")).toBe("en-US");
    expect(document.documentElement.lang).toBe("en-US");
  });

  it("restores a stored locale", () => {
    localStorage.setItem("pagecap-locale", "en-US");
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByTestId("locale")).toHaveTextContent("en-US");
  });

  it("falls back to the key itself for a missing translation", () => {
    render(<I18nProvider><Probe /></I18nProvider>);
    expect(screen.getByTestId("missing")).toHaveTextContent("no-such-key");
  });

  it("throws when used outside the provider, instead of silently rendering keys", () => {
    // React re-throws render errors through a jsdom "error" event as well as
    // console.error, so both channels are muted for this deliberate failure —
    // otherwise a passing suite prints an alarming stack trace.
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const swallow = (e: ErrorEvent) => e.preventDefault();
    window.addEventListener("error", swallow);
    try {
      expect(() => renderHook(() => useI18n())).toThrow(/I18nProvider/);
    } finally {
      window.removeEventListener("error", swallow);
      consoleSpy.mockRestore();
    }
  });

  it("keeps both dictionaries in sync", () => {
    // A key present in one language and missing in the other renders as a raw
    // key for half the users — the kind of thing only a test notices.
    expect(Object.keys(DICTIONARIES["pt-BR"]).sort()).toEqual(
      Object.keys(DICTIONARIES["en-US"]).sort(),
    );
  });

  it("has no empty translations", () => {
    for (const [locale, dict] of Object.entries(DICTIONARIES)) {
      for (const [key, value] of Object.entries(dict)) {
        expect(value.trim(), `${locale}.${key} is empty`).not.toBe("");
      }
    }
  });
});
