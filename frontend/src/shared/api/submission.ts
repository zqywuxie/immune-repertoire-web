import { ApiError, apiClient } from "./client";

const INPUT_VALIDATION_RETRY_DELAY_MS = 1000;
const INPUT_VALIDATION_MAX_RETRIES = 30;

function isInputValidationPending(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 400 || !error.payload || typeof error.payload !== "object") {
    return false;
  }
  const payload = error.payload as {
    error?: unknown;
    details?: { input_quality?: { inputs?: Array<{ status?: unknown }> } };
  };
  return payload.error === "VALIDATION_ERROR"
    && payload.details?.input_quality?.inputs?.some((input) => input.status === "pending") === true;
}

export async function postAfterInputValidation<T>(path: string, payload: unknown): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await apiClient.post<T>(path, payload);
    } catch (error) {
      if (!isInputValidationPending(error) || attempt >= INPUT_VALIDATION_MAX_RETRIES) throw error;
      await new Promise((resolve) => setTimeout(resolve, INPUT_VALIDATION_RETRY_DELAY_MS));
    }
  }
}
