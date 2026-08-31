/**
 * The reminder that repositories are still waiting for the project's workflows.
 *
 * The point of these tests is the register as much as the content: nothing is
 * broken when a repo hasn't been delivered to, so this must never present as a
 * warning — no alert role, no amber.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

import PendingDeliveryNotice from "./PendingDeliveryNotice";

describe("PendingDeliveryNotice", () => {
  it("renders nothing when no repository is waiting", () => {
    const { container } = render(<PendingDeliveryNotice repos={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the repository when only one is waiting", () => {
    render(<PendingDeliveryNotice repos={["acme/checkout-web"]} />);

    expect(
      screen.getByText("acme/checkout-web doesn't have this project's workflows yet"),
    ).toBeInTheDocument();
  });

  it("counts them and lists them when several are waiting", () => {
    render(<PendingDeliveryNotice repos={["acme/checkout-web", "acme/billing-api"]} />);

    expect(
      screen.getByText("2 repositories don't have this project's workflows yet"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("pending-delivery-notice"),
    ).toHaveTextContent("acme/checkout-web, acme/billing-api");
  });

  it("is not announced as an alert — nothing is wrong", () => {
    render(<PendingDeliveryNotice repos={["acme/checkout-web"]} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    const notice = screen.getByTestId("pending-delivery-notice");
    expect(notice.className).not.toMatch(/amber/);
    expect(notice.className).toMatch(/blue/);
  });

  it("says there is no hurry", () => {
    render(<PendingDeliveryNotice repos={["acme/checkout-web"]} />);

    expect(screen.getByTestId("pending-delivery-notice")).toHaveTextContent(
      /whenever it's convenient/i,
    );
  });

  it("offers the action, singular or plural to match", async () => {
    const onCreatePullRequests = vi.fn();
    const { rerender } = render(
      <PendingDeliveryNotice
        repos={["acme/checkout-web"]}
        onCreatePullRequests={onCreatePullRequests}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Create pull request" }));
    expect(onCreatePullRequests).toHaveBeenCalledTimes(1);

    rerender(
      <PendingDeliveryNotice
        repos={["acme/checkout-web", "acme/billing-api"]}
        onCreatePullRequests={onCreatePullRequests}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Create pull requests" }),
    ).toBeInTheDocument();
  });

  it("hides the action for a read-only viewer", () => {
    render(<PendingDeliveryNotice repos={["acme/checkout-web"]} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    // The reminder itself still renders — it is information, not a control.
    expect(screen.getByTestId("pending-delivery-notice")).toBeInTheDocument();
  });
});
