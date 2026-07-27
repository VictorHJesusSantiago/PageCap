import React from "react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "jest-axe";
import { JobState } from "@pagecap/core";
import { renderWithProviders, screen, userEvent, waitFor } from "../test/render";
import { ProgressPanel } from "./ProgressPanel";
import { ThemeToggle } from "./ThemeToggle";
import { LanguageToggle } from "./LanguageToggle";
import { JobHistory } from "./JobHistory";
import { ExtractionForm } from "./ExtractionForm";

vi.mock("../apiClient", () => ({
  client: { listJobs: vi.fn().mockResolvedValue([]) },
}));
import { client } from "../apiClient";

function job(overrides: Partial<JobState> = {}): JobState {
  return {
    job_id: "j1",
    status: "running",
    url: "https://example.com",
    progress: 42,
    total: 0,
    message: "Escaneando...",
    files: [],
    created_at: 1_700_000_000,
    updated_at: 1_700_000_010,
    ...overrides,
  } as JobState;
}

describe("ProgressPanel", () => {
  it("exposes progress to assistive tech, not just as a styled bar", () => {
    renderWithProviders(<ProgressPanel job={job()} phase="running" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("announces stage messages politely", () => {
    renderWithProviders(<ProgressPanel job={job()} phase="running" />);
    expect(screen.getByText("Escaneando...").closest("[aria-live]")).toHaveAttribute(
      "aria-live",
      "polite",
    );
  });

  it("offers pause while running and resume while paused", async () => {
    const onPause = vi.fn();
    const onResume = vi.fn();
    const user = userEvent.setup();

    const { unmount } = renderWithProviders(
      <ProgressPanel job={job()} phase="running" onPause={onPause} onResume={onResume} />,
    );
    await user.click(screen.getByRole("button", { name: "Pausar" }));
    expect(onPause).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Retomar" })).not.toBeInTheDocument();
    unmount();

    renderWithProviders(
      <ProgressPanel job={job({ status: "paused" })} phase="running" onPause={onPause} onResume={onResume} />,
    );
    await user.click(screen.getByRole("button", { name: "Retomar" }));
    expect(onResume).toHaveBeenCalledOnce();
  });

  it("calls onCancel", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<ProgressPanel job={job()} phase="running" onCancel={onCancel} />);
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("hides the action buttons once the job is finished", () => {
    renderWithProviders(
      <ProgressPanel job={job({ status: "done", progress: 100 })} phase="done" onCancel={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "Cancelar" })).not.toBeInTheDocument();
  });

  it("shows byte-level progress for the file currently downloading", () => {
    renderWithProviders(
      <ProgressPanel
        job={job({ current_file: { filename: "big.mp4", bytes_done: 512, bytes_total: 2048 } })}
        phase="running"
      />,
    );
    expect(screen.getByText("big.mp4")).toBeInTheDocument();
    expect(screen.getByText(/512 B/)).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderWithProviders(<ProgressPanel job={job()} phase="running" onCancel={vi.fn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("ThemeToggle", () => {
  it("is named for screen readers and reports its state", () => {
    renderWithProviders(<ThemeToggle theme="dark" onToggle={vi.fn()} />);
    const btn = screen.getByRole("button", { name: "Alternar tema claro/escuro" });
    expect(btn).toHaveAttribute("aria-pressed", "true");
  });

  it("toggles", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<ThemeToggle theme="light" onToggle={onToggle} />);
    await user.click(screen.getByRole("button"));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("has no axe violations", async () => {
    const { container } = renderWithProviders(<ThemeToggle theme="dark" onToggle={vi.fn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("LanguageToggle", () => {
  it("labels itself in the target language and tags that language", () => {
    renderWithProviders(<LanguageToggle />);
    const btn = screen.getByRole("button", { name: "Switch to English" });
    expect(btn).toHaveAttribute("lang", "en");
  });

  it("switches locale on click", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LanguageToggle />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByRole("button", { name: "Mudar para português" })).toBeInTheDocument();
  });
});

describe("JobHistory", () => {
  it("is collapsed until opened", async () => {
    renderWithProviders(<JobHistory onSelect={vi.fn()} />);
    const toggle = screen.getByRole("button", { name: /Histórico de jobs/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("loads jobs when opened and lets one be selected", async () => {
    vi.mocked(client.listJobs).mockResolvedValue([job({ job_id: "abc", status: "done" })]);
    const onSelect = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<JobHistory onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: /Histórico de jobs/ }));
    await waitFor(() => expect(screen.getByText("https://example.com")).toBeInTheDocument());

    await user.click(screen.getByText("https://example.com"));
    expect(onSelect).toHaveBeenCalledWith("abc");
  });

  it("shows an empty state when there is no history", async () => {
    vi.mocked(client.listJobs).mockResolvedValue([]);
    const user = userEvent.setup();
    renderWithProviders(<JobHistory onSelect={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Histórico de jobs/ }));
    await waitFor(() => expect(screen.getByText("Nenhum job ainda.")).toBeInTheDocument());
  });

  it("keeps the existing list when the API is unreachable", async () => {
    vi.mocked(client.listJobs).mockRejectedValue(new Error("offline"));
    const user = userEvent.setup();
    renderWithProviders(<JobHistory onSelect={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Histórico de jobs/ }));
    await waitFor(() => expect(screen.getByText("Nenhum job ainda.")).toBeInTheDocument());
  });

  it("names the refresh control", async () => {
    vi.mocked(client.listJobs).mockResolvedValue([]);
    const user = userEvent.setup();
    renderWithProviders(<JobHistory onSelect={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Histórico de jobs/ }));
    expect(screen.getByRole("button", { name: "Atualizar histórico" })).toBeInTheDocument();
  });
});

describe("ExtractionForm", () => {
  it("submits the URL and the default content type", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<ExtractionForm onSubmit={onSubmit} />);

    await user.type(screen.getByRole("textbox"), "https://example.com");
    await user.click(screen.getByRole("button", { name: /Extrair/ }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      url: "https://example.com",
      content_types: ["all"],
    });
  });

  it("does not submit an empty URL", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<ExtractionForm onSubmit={onSubmit} />);
    await user.click(screen.getByRole("button", { name: /Extrair/ }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("sends credentials only when that auth method is selected", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<ExtractionForm onSubmit={onSubmit} />);

    await user.type(screen.getByRole("textbox"), "https://example.com");
    await user.click(screen.getByRole("button", { name: "Login/Senha" }));
    await user.type(screen.getByPlaceholderText(/Usuário/), "alice");
    await user.type(screen.getByPlaceholderText("Senha"), "hunter2");
    await user.click(screen.getByRole("button", { name: /Extrair/ }));

    expect(onSubmit.mock.calls[0][0].auth).toMatchObject({
      method: "credentials",
      username: "alice",
      password: "hunter2",
    });
  });

  it("replaces 'all' when a specific type is picked", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<ExtractionForm onSubmit={onSubmit} />);

    await user.type(screen.getByRole("textbox"), "https://example.com");
    await user.click(screen.getByRole("button", { name: /Vídeos/ }));
    await user.click(screen.getByRole("button", { name: /Extrair/ }));

    expect(onSubmit.mock.calls[0][0].content_types).toEqual(["videos"]);
  });

  it("disables every control while a job is running", () => {
    renderWithProviders(<ExtractionForm onSubmit={vi.fn()} disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /Extraindo/ })).toBeDisabled();
  });

  it("accepts an http(s) URL dropped onto the form", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<ExtractionForm onSubmit={onSubmit} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;

    const dataTransfer = {
      getData: (type: string) => (type === "text/uri-list" ? "https://dropped.example/x" : ""),
    };
    const row = input.parentElement!;
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.drop(row, { dataTransfer });

    await waitFor(() => expect(input.value).toBe("https://dropped.example/x"));
  });

  it("ignores a dropped non-http URL", async () => {
    renderWithProviders(<ExtractionForm onSubmit={vi.fn()} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    const dataTransfer = { getData: () => "file:///etc/passwd" };
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.drop(input.parentElement!, { dataTransfer });
    expect(input.value).toBe("");
  });

  it("reveals advanced options on demand", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ExtractionForm onSubmit={vi.fn()} />);
    expect(screen.queryByLabelText(/Padrão de URL/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Opções avançadas/ }));
    expect(screen.getByLabelText(/Padrão de URL/)).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderWithProviders(<ExtractionForm onSubmit={vi.fn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
