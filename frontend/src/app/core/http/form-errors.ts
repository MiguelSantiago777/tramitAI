import { FormGroup } from '@angular/forms';

import { ApiError } from './api-error';

/**
 * Põe os erros de validação do backend (`details` por campo) nos controles do formulário,
 * como erro `server`. Devolve as mensagens que não couberam em nenhum campo.
 *
 * `aliases` mapeia nome do campo na API → nome do controle (ex.: responsible_id → responsible).
 */
export function applyServerErrors(
  form: FormGroup,
  error: ApiError,
  aliases: Record<string, string> = {},
): string[] {
  if (error.code !== 'validation_error' || !error.details) {
    return [error.message];
  }
  const leftovers: string[] = [];
  for (const [field, messages] of Object.entries(error.details)) {
    const text = flatten(messages).join(' ');
    const control = form.get(aliases[field] ?? field);
    if (control) {
      control.setErrors({ ...control.errors, server: text });
      control.markAsTouched();
    } else {
      leftovers.push(text);
    }
  }
  return leftovers;
}

function flatten(value: unknown): string[] {
  if (typeof value === 'string') {
    return [value];
  }
  if (Array.isArray(value)) {
    return value.flatMap(flatten);
  }
  if (value && typeof value === 'object') {
    return Object.values(value).flatMap(flatten);
  }
  return [];
}
