/**
 * Unit tests for time formatting utilities
 */

import { formatRelativeTime } from "./timeFormat";

describe("formatRelativeTime", () => {
  beforeEach(() => {
    // Mock the current time for consistent testing
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2024-01-15T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("should return 'just now' for times less than 60 seconds ago", () => {
    const time = new Date("2024-01-15T11:59:30Z").toISOString();
    expect(formatRelativeTime(time)).toBe("just now");
  });

  it("should return minutes for times less than 60 minutes ago", () => {
    const time = new Date("2024-01-15T11:45:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("15 minutes ago");
  });

  it("should return singular 'minute' for 1 minute ago", () => {
    const time = new Date("2024-01-15T11:59:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("1 minute ago");
  });

  it("should return hours for times less than 24 hours ago", () => {
    const time = new Date("2024-01-15T09:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("3 hours ago");
  });

  it("should return singular 'hour' for 1 hour ago", () => {
    const time = new Date("2024-01-15T11:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("1 hour ago");
  });

  it("should return days for times less than 7 days ago", () => {
    const time = new Date("2024-01-13T12:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("2 days ago");
  });

  it("should return singular 'day' for 1 day ago", () => {
    const time = new Date("2024-01-14T12:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("1 day ago");
  });

  it("should return weeks for times less than 4 weeks ago", () => {
    const time = new Date("2024-01-01T12:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("2 weeks ago");
  });

  it("should return singular 'week' for 1 week ago", () => {
    const time = new Date("2024-01-08T12:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("1 week ago");
  });

  it("should return months for times less than 12 months ago", () => {
    const time = new Date("2023-11-15T12:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("2 months ago");
  });

  it("should return singular 'month' for 1 month ago", () => {
    const time = new Date("2023-12-15T12:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("1 month ago");
  });

  it("should return years for times more than 12 months ago", () => {
    const time = new Date("2022-01-15T12:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("2 years ago");
  });

  it("should return singular 'year' for 1 year ago", () => {
    const time = new Date("2023-01-15T12:00:00Z").toISOString();
    expect(formatRelativeTime(time)).toBe("1 year ago");
  });
});
