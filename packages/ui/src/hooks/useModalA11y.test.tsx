import React, { useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, userEvent, waitFor } from "../test/render";
import { useModalA11y } from "./useModalA11y";

function Harness({ withFocusables = true }: { withFocusables?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useModalA11y(open, () => setOpen(false));
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        open
      </button>
      <button type="button">outside</button>
      {open && (
        <div ref={ref} role="dialog" aria-modal="true" aria-label="dlg" tabIndex={-1}>
          {withFocusables ? (
            <>
              <button type="button">first</button>
              <button type="button">last</button>
            </>
          ) : (
            <p>nothing focusable</p>
          )}
        </div>
      )}
    </div>
  );
}

describe("useModalA11y", () => {
  it("moves focus into the dialog on open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("open"));
    expect(screen.getByText("first")).toHaveFocus();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("open"));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("restores focus to the trigger on close", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const trigger = screen.getByText("open");
    await user.click(trigger);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("wraps Tab from the last element back to the first", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("open"));

    expect(screen.getByText("first")).toHaveFocus();
    await user.tab();
    expect(screen.getByText("last")).toHaveFocus();
    await user.tab();
    expect(screen.getByText("first")).toHaveFocus();
  });

  it("wraps Shift+Tab from the first element to the last", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("open"));

    await user.tab({ shift: true });
    expect(screen.getByText("last")).toHaveFocus();
  });

  it("never lets focus escape to elements behind the dialog", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("open"));

    for (let i = 0; i < 8; i++) await user.tab();
    expect(screen.getByText("outside")).not.toHaveFocus();
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("focuses the container when the dialog holds nothing focusable", async () => {
    const user = userEvent.setup();
    render(<Harness withFocusables={false} />);
    await user.click(screen.getByText("open"));
    expect(screen.getByRole("dialog")).toHaveFocus();
  });

  it("keeps Tab inside an empty dialog", async () => {
    const user = userEvent.setup();
    render(<Harness withFocusables={false} />);
    await user.click(screen.getByText("open"));
    await user.tab();
    expect(screen.getByText("outside")).not.toHaveFocus();
  });
});
