import React, { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import { I18nProvider } from "../i18n";

export function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, {
    wrapper: ({ children }) => <I18nProvider>{children}</I18nProvider>,
    ...options,
  });
}

export * from "@testing-library/react";
export { default as userEvent } from "@testing-library/user-event";
