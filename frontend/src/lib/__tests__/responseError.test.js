import { describe, it, expect } from "vitest";
import {
  errorMessageFromResponse,
  messageFromErrorBody,
  messageForCaughtError,
} from "../responseError";

const jsonResponse = (status, body) => ({ ok: false, status, json: async () => body });
const htmlResponse = (status) => ({
  ok: false,
  status,
  json: async () => {
    throw new SyntaxError("Unexpected token '<'");
  },
});

describe("errorMessageFromResponse", () => {
  it("names the field and gives the server's reason for a validation error", async () => {
    // The body the backend returned for an admin email on a reserved domain.
    const res = jsonResponse(422, {
      error: "VALIDATION_ERROR",
      message: "Request validation failed",
      details: {
        errors: [
          {
            field: "email",
            message:
              "value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email.",
            type: "value_error",
          },
        ],
      },
    });
    const message = await errorMessageFromResponse(res, "Setup failed", { email: "Email Address" });
    expect(message).toBe(
      "Email Address: The part after the @-sign is a special-use or reserved name that cannot be used with email.",
    );
  });

  it("joins several field errors and humanises fields without a label", async () => {
    const res = jsonResponse(422, {
      error: "VALIDATION_ERROR",
      message: "Request validation failed",
      details: {
        errors: [
          { field: "password", message: "String should have at least 8 characters" },
          { field: "full_name", message: "Value error, name is required" },
        ],
      },
    });
    expect(await errorMessageFromResponse(res, "Setup failed", { password: "Password" })).toBe(
      "Password: String should have at least 8 characters Full name: Name is required",
    );
  });

  it("uses a plain detail string", async () => {
    const res = jsonResponse(400, { detail: "Setup has already been completed" });
    expect(await errorMessageFromResponse(res, "Setup failed")).toBe("Setup has already been completed");
  });

  it("reads FastAPI's default list-style detail", async () => {
    const res = jsonResponse(422, { detail: [{ loc: ["body", "email"], msg: "field required" }] });
    expect(await errorMessageFromResponse(res, "Setup failed", { email: "Email Address" })).toBe(
      "Email Address: Field required",
    );
  });

  it("shows the rate-limit text", async () => {
    const res = jsonResponse(429, { error: "Rate limit exceeded: 3 per 1 minute" });
    expect(await errorMessageFromResponse(res, "Setup failed")).toBe("Rate limit exceeded: 3 per 1 minute");
  });

  it("explains a proxy error page instead of a JSON parse error", async () => {
    expect(await errorMessageFromResponse(htmlResponse(502), "Setup failed")).toBe(
      "FilaOps isn't responding right now. Wait a minute and try again.",
    );
  });

  it("falls back to the caller's text with the status code", async () => {
    expect(await errorMessageFromResponse(htmlResponse(500), "Setup failed")).toBe("Setup failed (error 500).");
    expect(await errorMessageFromResponse(jsonResponse(500, {}), "Import failed")).toBe("Import failed (error 500).");
  });
});

describe("messageFromErrorBody", () => {
  it("ignores the generic validation headline when there are no field errors", () => {
    expect(messageFromErrorBody({ error: "VALIDATION_ERROR", message: "Request validation failed" })).toBe("");
  });

  it("uses a specific message", () => {
    expect(messageFromErrorBody({ error: "CONFLICT", message: "That SKU already exists" })).toBe(
      "That SKU already exists",
    );
  });
});

describe("messageForCaughtError", () => {
  it("explains a network failure", () => {
    expect(messageForCaughtError(new TypeError("Failed to fetch"))).toBe(
      "Cannot reach the FilaOps server. Check that FilaOps is running, then try again.",
    );
    expect(messageForCaughtError(new TypeError("Load failed"))).toMatch(/Cannot reach the FilaOps server/);
  });

  it("keeps other errors as they are", () => {
    expect(messageForCaughtError(new Error("Email Address: bad"))).toBe("Email Address: bad");
    expect(messageForCaughtError(new TypeError("x is undefined"))).toBe("x is undefined");
  });
});
