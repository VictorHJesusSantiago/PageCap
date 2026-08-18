
import type { TestingLibraryMatchers } from "@testing-library/jest-dom/matchers";

interface AxeMatchers<R = unknown> {
  toHaveNoViolations(): R;
}

declare module "vitest" {
  interface Assertion<T = any> extends TestingLibraryMatchers<T, void>, AxeMatchers<void> {}
  interface AsymmetricMatchersContaining
      extends TestingLibraryMatchers<any, void>,
      AxeMatchers<void> {}
}
