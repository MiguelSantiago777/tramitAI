import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

/** Mesmas regras de backend/apps/core/br.py e backend/apps/processos/cnj.py. */

export const onlyDigits = (value: string | null | undefined): string =>
  (value ?? '').replace(/\D/g, '');

export const normalizeDocument = (value: string | null | undefined): string =>
  (value ?? '').replace(/[\s./-]/g, '').toUpperCase();

export function isValidCpf(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) {
    return false;
  }
  for (const size of [9, 10]) {
    let total = 0;
    for (let i = 0; i < size; i++) {
      total += Number(d[i]) * (size + 1 - i);
    }
    if (((total * 10) % 11) % 10 !== Number(d[size])) {
      return false;
    }
  }
  return true;
}

const CNPJ_WEIGHTS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
const CNPJ_WEIGHTS_2 = [6, ...CNPJ_WEIGHTS_1];

/** CNPJ numérico ou alfanumérico (IN RFB 2.229/2024). */
export function isValidCnpj(value: string): boolean {
  const doc = normalizeDocument(value);
  if (!/^[A-Z0-9]{12}\d{2}$/.test(doc) || /^(.)\1{13}$/.test(doc)) {
    return false;
  }
  const values = [...doc].map((c) => c.charCodeAt(0) - 48);
  for (const [weights, position] of [
    [CNPJ_WEIGHTS_1, 12],
    [CNPJ_WEIGHTS_2, 13],
  ] as const) {
    const remainder = weights.reduce((sum, w, i) => sum + w * values[i], 0) % 11;
    const check = remainder < 2 ? 0 : 11 - remainder;
    if (check !== values[position]) {
      return false;
    }
  }
  return true;
}

/** Telefone BR em E.164 (+55...) ou null. */
export function normalizeBrPhone(value: string): string | null {
  let d = onlyDigits(value);
  if (d.startsWith('55') && (d.length === 12 || d.length === 13)) {
    d = d.slice(2);
  }
  if (d.length !== 10 && d.length !== 11) {
    return null;
  }
  const [ddd, number] = [d.slice(0, 2), d.slice(2)];
  if (ddd[0] === '0' || ddd[1] === '0') {
    return null;
  }
  if (number.length === 9 && number[0] !== '9') {
    return null;
  }
  if (number.length === 8 && !'2345'.includes(number[0])) {
    return null;
  }
  return `+55${d}`;
}

export function isValidCnj(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 20) {
    return false;
  }
  return BigInt(d.slice(0, 7) + d.slice(9) + d.slice(7, 9)) % 97n === 1n;
}

export function formatCnj(value: string): string {
  const d = onlyDigits(value);
  if (d.length !== 20) {
    return value;
  }
  return `${d.slice(0, 7)}-${d.slice(7, 9)}.${d.slice(9, 13)}.${d[13]}.${d.slice(14, 16)}.${d.slice(16)}`;
}

export function formatDocument(value: string): string {
  const doc = normalizeDocument(value);
  if (doc.length === 11) {
    return doc.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
  }
  if (doc.length === 14) {
    return doc.replace(/^(\w{2})(\w{3})(\w{3})(\w{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  }
  return value;
}

export function formatPhone(e164: string): string {
  const d = onlyDigits(e164).replace(/^55/, '');
  if (d.length === 11) {
    return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  }
  if (d.length === 10) {
    return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  }
  return e164;
}

// ---------------------------------------------------------------- validators

export const cnjValidator: ValidatorFn = (c: AbstractControl): ValidationErrors | null =>
  !c.value || isValidCnj(c.value) ? null : { cnj: true };

export const phoneValidator: ValidatorFn = (c: AbstractControl): ValidationErrors | null =>
  !c.value || normalizeBrPhone(c.value) ? null : { phone: true };

/** Valida CPF ou CNPJ conforme o tipo de pessoa. Revalide quando o tipo mudar. */
export function documentValidator(kind: () => 'PF' | 'PJ'): ValidatorFn {
  return (c: AbstractControl): ValidationErrors | null => {
    if (!c.value) {
      return null;
    }
    if (kind() === 'PF') {
      return isValidCpf(c.value) ? null : { cpf: true };
    }
    return isValidCnpj(c.value) ? null : { cnpj: true };
  };
}
