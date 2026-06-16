import { resolveAppError } from "./engine";
import type { GenerateVideoResult } from "./engine";

export function resolveResultError(result: GenerateVideoResult) {
  if (result.code) {
    return resolveAppError(`[${result.code}] ${result.message}`);
  }
  return resolveAppError(result.message);
}

