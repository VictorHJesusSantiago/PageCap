// Ambient declarations for `jest-axe`, which ships no types of its own.
// This file must contain no top-level import/export: that would make it a
// module, and `declare module` inside a module augments an existing one instead
// of declaring a new one.
//
// Only the surface this project actually uses is typed.
declare module "jest-axe" {
  export interface AxeResults {
    violations: Array<{
      id: string;
      impact: string | null;
      description: string;
      help: string;
      helpUrl: string;
      nodes: Array<{ html: string; target: string[]; failureSummary?: string }>;
    }>;
    passes: unknown[];
    incomplete: unknown[];
    inapplicable: unknown[];
  }

  export function axe(
    html: Element | string,
    options?: Record<string, unknown>,
  ): Promise<AxeResults>;

  export function configureAxe(options?: Record<string, unknown>): typeof axe;

  export const toHaveNoViolations: {
    toHaveNoViolations(results: AxeResults): {
      pass: boolean;
      actual: unknown;
      message(): string;
    };
  };
}
