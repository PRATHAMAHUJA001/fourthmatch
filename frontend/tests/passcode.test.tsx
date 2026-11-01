import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PasscodeDialog } from "../src/components/shell/PasscodeDialog";
import { api, ApiError, getPasscode, registerPasscodePrompt, setPasscode } from "../src/lib/api";

const errBody = (code: string, message: string, status: number) =>
  new Response(JSON.stringify({ error: { code, message, request_id: "r" } }), { status, headers: { "Content-Type": "application/json" } });
const ok = (body: unknown = { id: 1 }) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
const headerOf = (call: unknown[], name: string) => new Headers((call[1] as RequestInit).headers).get(name);

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  setPasscode(null);
  registerPasscodePrompt(null);
});
afterEach(() => { vi.unstubAllGlobals(); setPasscode(null); registerPasscodePrompt(null); });

describe("demo passcode in the API layer", () => {
  it("sends X-Demo-Passcode on non-GET only, when one is stored", async () => {
    setPasscode("open-sesame");
    fetchMock.mockImplementation(() => Promise.resolve(ok()));
    await api.approveRule(3);
    await api.cases();
    expect(headerOf(fetchMock.mock.calls[0], "X-Demo-Passcode")).toBe("open-sesame");
    expect(headerOf(fetchMock.mock.calls[1], "X-Demo-Passcode")).toBeNull();
  });

  it("sends no header when no passcode is stored", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(ok()));
    await api.rejectRule(3);
    expect(headerOf(fetchMock.mock.calls[0], "X-Demo-Passcode")).toBeNull();
  });

  it("on demo_passcode_required asks once, stores the code and retries once", async () => {
    const prompt = vi.fn().mockResolvedValue("letmein");
    registerPasscodePrompt(prompt);
    fetchMock
      .mockResolvedValueOnce(errBody("demo_passcode_required", "A valid demo passcode is required for this action.", 403))
      .mockResolvedValueOnce(ok({ done: true }));
    await expect(api.approveRule(1)).resolves.toEqual({ done: true });
    expect(prompt).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(headerOf(fetchMock.mock.calls[1], "X-Demo-Passcode")).toBe("letmein");
    expect(getPasscode()).toBe("letmein");
  });

  it("does not loop: a rejected passcode is forgotten and the error surfaces after one retry", async () => {
    registerPasscodePrompt(vi.fn().mockResolvedValue("wrong"));
    fetchMock.mockImplementation(() => Promise.resolve(errBody("demo_passcode_required", "A valid demo passcode is required for this action.", 403)));
    const err = await api.approveRule(1).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("demo_passcode_required");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getPasscode()).toBeNull();
  });

  it("cancelling the prompt throws without retrying", async () => {
    registerPasscodePrompt(vi.fn().mockResolvedValue(null));
    fetchMock.mockResolvedValue(errBody("demo_passcode_required", "needs code", 403));
    await expect(api.approveRule(1)).rejects.toThrow("needs code");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows live_uploads_disabled and upload_rate_limited messages as-is, without prompting", async () => {
    const prompt = vi.fn();
    registerPasscodePrompt(prompt);
    fetchMock.mockResolvedValueOnce(errBody("live_uploads_disabled", "Changes are disabled on this demo.", 403));
    await expect(api.createDelivery(1)).rejects.toThrow("Changes are disabled on this demo.");
    fetchMock.mockResolvedValueOnce(errBody("upload_rate_limited", "Live upload limit reached (10 per hour). Try again in about 12 minute(s).", 429));
    const err = (await api.createDelivery(1).catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(429);
    expect(err.message).toContain("Try again in about 12 minute(s)");
    expect(prompt).not.toHaveBeenCalled();
  });

  it("never prompts for a GET", async () => {
    const prompt = vi.fn();
    registerPasscodePrompt(prompt);
    fetchMock.mockResolvedValue(errBody("demo_passcode_required", "needs code", 403));
    await expect(api.cases()).rejects.toThrow();
    expect(prompt).not.toHaveBeenCalled();
  });

  it("the dialog collects the passcode and the request is retried with it", async () => {
    render(<PasscodeDialog />);
    fetchMock
      .mockResolvedValueOnce(errBody("demo_passcode_required", "needs code", 403))
      .mockResolvedValueOnce(ok({ ok: 1 }));
    const pending = api.approveRule(9);
    const input = await screen.findByLabelText("Passcode");
    fireEvent.change(input, { target: { value: "hunter2" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await expect(pending).resolves.toEqual({ ok: 1 });
    expect(headerOf(fetchMock.mock.calls[1], "X-Demo-Passcode")).toBe("hunter2");
  });
});
