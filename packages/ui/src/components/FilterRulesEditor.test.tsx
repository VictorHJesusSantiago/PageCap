import React, { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "jest-axe";
import { render, screen, userEvent } from "../test/render";
import { FilterRulesEditor } from "./FilterRulesEditor";

function Controlled({ initial = [] as string[] }) {
  const [exts, setExts] = useState<string[]>(initial);
  const [pattern, setPattern] = useState("");
  const [size, setSize] = useState(0);
  return (
    <FilterRulesEditor
      extensions={exts}
      onExtensionsChange={setExts}
      urlPattern={pattern}
      onUrlPatternChange={setPattern}
      minSizeBytes={size}
      onMinSizeBytesChange={setSize}
    />
  );
}

describe("extension chips", () => {
  it("normalises a bare extension by prefixing a dot", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    await user.type(screen.getByLabelText(/Extensões específicas/), "pdf");
    await user.click(screen.getByRole("button", { name: "Adicionar extensão" }));
    expect(screen.getByText(".pdf")).toBeInTheDocument();
  });

  it("lowercases the extension", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    await user.type(screen.getByLabelText(/Extensões específicas/), ".PDF{Enter}");
    expect(screen.getByText(".pdf")).toBeInTheDocument();
  });

  it("adds on Enter and on comma", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText(/Extensões específicas/);
    await user.type(input, ".pdf{Enter}");
    await user.type(input, ".mp3,");
    expect(screen.getByText(".pdf")).toBeInTheDocument();
    expect(screen.getByText(".mp3")).toBeInTheDocument();
  });

  it("clears the draft after adding", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText(/Extensões específicas/) as HTMLInputElement;
    await user.type(input, ".pdf{Enter}");
    expect(input.value).toBe("");
  });

  it("ignores duplicates", async () => {
    const user = userEvent.setup();
    render(<Controlled initial={[".pdf"]} />);
    await user.type(screen.getByLabelText(/Extensões específicas/), ".pdf{Enter}");
    expect(screen.getAllByText(".pdf")).toHaveLength(1);
  });

  it("ignores whitespace-only input", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <FilterRulesEditor
        extensions={[]}
        onExtensionsChange={onChange}
        urlPattern=""
        onUrlPatternChange={() => {}}
        minSizeBytes={0}
        onMinSizeBytesChange={() => {}}
      />,
    );
    await user.type(screen.getByLabelText(/Extensões específicas/), "   {Enter}");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("removes a chip", async () => {
    const user = userEvent.setup();
    render(<Controlled initial={[".pdf", ".mp3"]} />);
    await user.click(screen.getByRole("button", { name: "Remover .pdf" }));
    expect(screen.queryByText(".pdf")).not.toBeInTheDocument();
    expect(screen.getByText(".mp3")).toBeInTheDocument();
  });

  it("disables the add button while the draft is empty", () => {
    render(<Controlled />);
    expect(screen.getByRole("button", { name: "Adicionar extensão" })).toBeDisabled();
  });
});

describe("size conversion", () => {
  it("converts the KB input to bytes", async () => {
    const onSize = vi.fn();
    const user = userEvent.setup();
    render(
      <FilterRulesEditor
        extensions={[]}
        onExtensionsChange={() => {}}
        urlPattern=""
        onUrlPatternChange={() => {}}
        minSizeBytes={0}
        onMinSizeBytesChange={onSize}
      />,
    );
    await user.type(screen.getByLabelText(/Tamanho mínimo/), "5");
    expect(onSize).toHaveBeenLastCalledWith(5 * 1024);
  });

  it("displays stored bytes back as KB", () => {
    render(
      <FilterRulesEditor
        extensions={[]}
        onExtensionsChange={() => {}}
        urlPattern=""
        onUrlPatternChange={() => {}}
        minSizeBytes={10 * 1024}
        onMinSizeBytesChange={() => {}}
      />,
    );
    expect(screen.getByLabelText(/Tamanho mínimo/)).toHaveValue(10);
  });

  it("never emits a negative size", async () => {
    const onSize = vi.fn();
    const user = userEvent.setup();
    render(
      <FilterRulesEditor
        extensions={[]}
        onExtensionsChange={() => {}}
        urlPattern=""
        onUrlPatternChange={() => {}}
        minSizeBytes={0}
        onMinSizeBytesChange={onSize}
      />,
    );
    await user.type(screen.getByLabelText(/Tamanho mínimo/), "-3");
    for (const call of onSize.mock.calls) expect(call[0]).toBeGreaterThanOrEqual(0);
  });
});

describe("disabled state", () => {
  it("disables every control", () => {
    render(
      <FilterRulesEditor
        extensions={[".pdf"]}
        onExtensionsChange={() => {}}
        urlPattern=""
        onUrlPatternChange={() => {}}
        minSizeBytes={0}
        onMinSizeBytesChange={() => {}}
        disabled
      />,
    );
    expect(screen.getByLabelText(/Extensões específicas/)).toBeDisabled();
    expect(screen.getByLabelText(/Padrão de URL/)).toBeDisabled();
    expect(screen.getByLabelText(/Tamanho mínimo/)).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remover .pdf" })).toBeDisabled();
  });
});

describe("axe", () => {
  it("has no violations and every field has an accessible name", async () => {
    const { container } = render(<Controlled initial={[".pdf"]} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
