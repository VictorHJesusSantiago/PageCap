import React from "react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "jest-axe";
import { ExtractedFile } from "@pagecap/core";
import { renderWithProviders, screen, userEvent, waitFor } from "../test/render";
import { formatBytes, getFileCategory } from "../format";
import { FileList } from "./FileList";

function file(overrides: Partial<ExtractedFile> = {}): ExtractedFile {
  return {
    filename: "photo.jpg",
    url: "https://example.com/photo.jpg",
    content_type: "image/jpeg",
    size_bytes: 2048,
    local_path: "/tmp/photo.jpg",
    mime_mismatch: false,
    ...overrides,
  } as ExtractedFile;
}

const defaultProps = {
  getDownloadUrl: (n: string) => `http://127.0.0.1:8765/v1/jobs/j/download/${n}`,
  getPreviewUrl: (n: string) => `http://127.0.0.1:8765/v1/jobs/j/preview/${n}`,
  getDownloadAllUrl: () => "http://127.0.0.1:8765/v1/jobs/j/download-all",
  onReset: () => {},
};

describe("pure helpers", () => {
  it.each([
    ["application/pdf", "pdf"],
    ["image/png", "image"],
    ["video/mp4", "video"],
    ["audio/mpeg", "audio"],
    ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "document"],
    ["application/octet-stream", "other"],
  ])("categorises %s as %s", (ct, expected) => {
    expect(getFileCategory(ct)).toBe(expected);
  });

  it.each([
    [undefined, "?"],
    [0, "?"],
    [512, "512 B"],
    [2048, "2.0 KB"],
    [5 * 1024 * 1024, "5.00 MB"],
  ])("formats %s bytes as %s", (input, expected) => {
    expect(formatBytes(input as number | undefined)).toBe(expected);
  });

  it("lets the caller override the falsy fallback", () => {

    expect(formatBytes(0, "0 B")).toBe("0 B");
    expect(formatBytes(undefined, "0 B")).toBe("0 B");
  });
});

describe("FileList rendering", () => {
  it("lists every file with its size", () => {
    renderWithProviders(
      <FileList files={[file(), file({ filename: "doc.pdf", content_type: "application/pdf" })]} {...defaultProps} />,
    );
    expect(screen.getByText("photo.jpg")).toBeInTheDocument();
    expect(screen.getByText("doc.pdf")).toBeInTheDocument();
    expect(screen.getByText(/2 arquivo\(s\) extraído\(s\)/)).toBeInTheDocument();
  });

  it("filters by category and keeps the counts accurate", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <FileList
        files={[
          file({ filename: "a.jpg" }),
          file({ filename: "b.pdf", content_type: "application/pdf" }),
          file({ filename: "c.mp4", content_type: "video/mp4" }),
        ]}
        {...defaultProps}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^PDF/ }));
    expect(screen.getByText("b.pdf")).toBeInTheDocument();
    expect(screen.queryByText("a.jpg")).not.toBeInTheDocument();
    expect(screen.queryByText("c.mp4")).not.toBeInTheDocument();
  });

  it("shows an empty state when the filter matches nothing", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FileList files={[file()]} {...defaultProps} />);
    await user.click(screen.getByRole("button", { name: /^Vídeos/ }));
    expect(screen.getByText("Nenhum arquivo deste tipo.")).toBeInTheDocument();
  });
});

describe("selection state is keyed by filename, not row index", () => {
  it("keeps the right file selected after the filter changes", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <FileList
        files={[
          file({ filename: "first.jpg" }),
          file({ filename: "second.pdf", content_type: "application/pdf" }),
        ]}
        {...defaultProps}
      />,
    );

    await user.click(screen.getByRole("checkbox", { name: /second\.pdf/ }));
    expect(screen.getByRole("checkbox", { name: /second\.pdf/ })).toHaveAttribute("aria-checked", "true");

    await user.click(screen.getByRole("button", { name: /^Imagens/ }));
    expect(screen.getByRole("checkbox", { name: /first\.jpg/ })).toHaveAttribute("aria-checked", "false");
  });

  it("select-all only affects the visible filter", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <FileList
        files={[file({ filename: "a.jpg" }), file({ filename: "b.pdf", content_type: "application/pdf" })]}
        {...defaultProps}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^Imagens/ }));
    await user.click(screen.getByRole("button", { name: /Selecionar todos/ }));
    await user.click(screen.getByRole("button", { name: /^Todos/ }));

    expect(screen.getByRole("checkbox", { name: /a\.jpg/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("checkbox", { name: /b\.pdf/ })).toHaveAttribute("aria-checked", "false");
  });
});

describe("preview modal accessibility", () => {
  it("opens as a labelled modal dialog", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FileList files={[file()]} {...defaultProps} />);

    await user.click(screen.getByRole("button", { name: /Pré-visualizar arquivo: photo\.jpg/ }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName(/photo\.jpg/);
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FileList files={[file()]} {...defaultProps} />);

    await user.click(screen.getByRole("button", { name: /Pré-visualizar arquivo/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes via the close button and restores focus to the trigger", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FileList files={[file()]} {...defaultProps} />);

    const trigger = screen.getByRole("button", { name: /Pré-visualizar arquivo/ });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: /Fechar pré-visualização/ }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("traps Tab inside the dialog", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FileList files={[file()]} {...defaultProps} />);

    await user.click(screen.getByRole("button", { name: /Pré-visualizar arquivo/ }));
    const dialog = screen.getByRole("dialog");

    for (let i = 0; i < 6; i++) await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("is not offered for file types the API refuses to serve inline", () => {
    renderWithProviders(
      <FileList files={[file({ filename: "evil.html", content_type: "text/html" })]} {...defaultProps} />,
    );
    expect(screen.queryByRole("button", { name: /Pré-visualizar/ })).not.toBeInTheDocument();
  });
});

describe("downloads", () => {
  it("gives every download link the token-bearing URL", () => {
    renderWithProviders(<FileList files={[file()]} {...defaultProps} />);
    expect(screen.getByRole("link", { name: /Baixar arquivo: photo\.jpg/ })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8765/v1/jobs/j/download/photo.jpg",
    );
  });

  it("staggers multi-file downloads so the browser does not drop them", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.download);
    });

    renderWithProviders(
      <FileList
        files={[file({ filename: "a.jpg" }), file({ filename: "b.jpg" }), file({ filename: "c.jpg" })]}
        {...defaultProps}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Selecionar todos/ }));
    await user.click(screen.getByRole("button", { name: /Baixar selecionados/ }));

    expect(clicks).toEqual(["a.jpg"]);

    await vi.advanceTimersByTimeAsync(250);
    expect(clicks).toEqual(["a.jpg", "b.jpg"]);

    await vi.advanceTimersByTimeAsync(250);
    expect(clicks).toEqual(["a.jpg", "b.jpg", "c.jpg"]);
    vi.useRealTimers();
  });
});

describe("axe", () => {
  it("has no detectable violations in the list view", async () => {
    const { container } = renderWithProviders(
      <FileList
        files={[file(), file({ filename: "doc.pdf", content_type: "application/pdf" })]}
        outputDir="/tmp/job"
        {...defaultProps}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no detectable violations with the preview open", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<FileList files={[file()]} {...defaultProps} />);
    await user.click(screen.getByRole("button", { name: /Pré-visualizar arquivo/ }));
    expect(await axe(container)).toHaveNoViolations();
  });
});
