import React, { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import { I18nProvider } from "../i18n";

/**
 * Renders a component inside the providers the real app supplies. Without this
 * every test that touches a translated string has to remember the provider, and
 * forgetting it throws from useI18n rather than failing an assertion.
 */
export function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, {
    wrapper: ({ children }) => <I18nProvider>{children}</I18nProvider>,
    ...options,
  });
}

export * from "@testing-library/react";
export { default as userEvent } from "@testing-library/user-event";
