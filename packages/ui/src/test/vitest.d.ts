/// <reference types="vitest/globals" />

// src/test/setup.ts extends Vitest's `expect` with the jest-dom matchers and
// jest-axe's toHaveNoViolations. Runtime registration does not teach TypeScript
// about them, so the Assertion interface is augmented here.
//
// The matchers are imported and registered manually (not via
// "@testing-library/jest-dom/vitest", which cannot resolve `vitest` from the
// hoisted root node_modules under npm workspaces), which is why this file has
// to declare them rather than relying on that package's own augmentation.
import type { TestingLibraryMatchers } from "@testing-library/jest-dom/matchers";

interface AxeMatchers<R = unknown> {
  toHaveNoViolations(): R;
}

declare module "vitest" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  interface Assertion<T = any> extends TestingLibraryMatchers<T, void>, AxeMatchers<void> {}
  interface AsymmetricMatchersContaining
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    extends TestingLibraryMatchers<any, void>,
      AxeMatchers<void> {}
}

// NB: the `jest-axe` module declaration lives in its own ambient file
// (jest-axe.d.ts). A `declare module` inside a file that has top-level imports
// is a module *augmentation* of an existing module, not a declaration of a new
// one, so it cannot supply types for an untyped package.
