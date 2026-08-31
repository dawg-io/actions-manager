import { errorDetail } from "./errorDetail";

describe("errorDetail", () => {
  it("prefers the server's response payload", () => {
    const error = {
      response: { data: { detail: "Project not found" } },
      message: "Request failed with status code 404",
    };

    expect(errorDetail(error)).toEqual({ detail: "Project not found" });
  });

  it("falls back to the message when there is no response payload", () => {
    expect(errorDetail(new Error("Network Error"))).toBe("Network Error");
  });

  // || not ??: an empty payload is useless to log, so it falls through the same
  // way it did before these call sites shared a helper.
  it("falls through a present but empty payload", () => {
    const error = { response: { data: "" }, message: "Bad Gateway" };

    expect(errorDetail(error)).toBe("Bad Gateway");
  });

  it("returns the value itself when it is neither", () => {
    expect(errorDetail("boom")).toBe("boom");
    expect(errorDetail(undefined)).toBeUndefined();
  });
});
