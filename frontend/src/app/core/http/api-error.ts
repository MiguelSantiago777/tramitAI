import { HttpErrorResponse } from '@angular/common/http';

/** Formato padrão de erro do backend: {"error": {"code", "message", "details?"}}. */
export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

function isApiErrorBody(body: unknown): body is { error: ApiError } {
  if (typeof body !== 'object' || body === null || !('error' in body)) {
    return false;
  }
  const error = (body as { error: unknown }).error;
  return typeof error === 'object' && error !== null && 'code' in error && 'message' in error;
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof HttpErrorResponse && isApiErrorBody(err.error)) {
    return err.error.error;
  }
  return {
    code: 'network_error',
    message: 'Não foi possível falar com o servidor. Tente novamente.',
  };
}
