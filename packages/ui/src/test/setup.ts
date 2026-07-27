import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup } from "@testing-library/react";
import { afterEach, expect, vi } from "vitest";
import { toHaveNoViolations } from "jest-axe";

// Extend explicitly rather than importing "@testing-library/jest-dom/vitest".
// That entry point does `import { expect } from "vitest"` itself, which fails
// under npm workspaces: jest-dom hoists to the root node_modules where vitest
// is not resolvable. Importing the matchers and extending here has no such
// dependency on hoisting layout.
expect.extend(matchers);
expect.extend(toHaveNoViolations as never);

// F.I.R.S.T — Independent: unmount everything between tests so a leaked
// component (or its event listeners) cannot influence the next one.
afterEach(() => {
  cleanup();
  localStorage.clear();
  // restoreAllMocks only undoes spies created with vi.spyOn. Call history on
  // the vi.fn()s inside a vi.mock() factory survives it, which silently leaks
  // call counts from one test into the next assertion.
  vi.clearAllMocks();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// jsdom implements neither of these, and both are used by the components under
// test (media preview, thumbnails).
if (!window.HTMLMediaElement.prototype.play) {
  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
}
Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: vi.fn().mockResolvedValue(undefined),
});

// matchMedia is required by anything reading prefers-color-scheme.
if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}
