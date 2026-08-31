import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import DarkModeToggle from "./DarkModeToggle";
import { ThemeProvider } from "./ThemeContext";

const renderToggle = (props: { className?: string } = {}) =>
  render(
    <ThemeProvider>
      <DarkModeToggle {...props} />
    </ThemeProvider>
  );

describe("DarkModeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test("offers to switch to light mode when the default dark theme is active", () => {
    renderToggle();

    const button = screen.getByRole("button", { name: "Switch to light mode" });
    expect(button).toHaveTextContent("☀️");
  });

  test("offers to switch back to dark mode after being clicked", () => {
    renderToggle();

    fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));

    const button = screen.getByRole("button", { name: "Switch to dark mode" });
    expect(button).toHaveTextContent("🌙");
  });

  test("reads the saved light-mode preference on mount", () => {
    localStorage.setItem("theme", "light");

    renderToggle();

    expect(
      screen.getByRole("button", { name: "Switch to dark mode" })
    ).toBeInTheDocument();
  });

  test("pins itself to the viewport by default", () => {
    renderToggle();

    expect(screen.getByRole("button")).toHaveClass("fixed", "top-6", "right-6");
  });

  test("renders inline when given any other className", () => {
    renderToggle({ className: "inline" });

    const button = screen.getByRole("button");
    expect(button).toHaveClass("static");
    expect(button).not.toHaveClass("top-6");
  });
});
