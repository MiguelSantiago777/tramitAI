export type AgreementKind = 'CONTRATUAL' | 'EXITO' | 'MENSAL' | 'CONSULTA' | 'OUTRO';
export type AgreementStatus = 'ACTIVE' | 'FINISHED' | 'CANCELLED';
export type InstallmentStatus = 'OPEN' | 'PAID' | 'CANCELLED';
export type PaymentMethod = 'PIX' | 'BOLETO' | 'CARTAO' | 'TRANSFERENCIA' | 'DINHEIRO' | 'OUTRO';
export type ChargeKind = '' | 'PIX' | 'LINK';
export type InstallmentFilter = '' | 'open' | 'overdue' | 'paid' | 'cancelled';

export interface Installment {
  id: string;
  agreement_id: string;
  agreement_title: string;
  client_id: string;
  client_name: string;
  case_number: string;
  number: number;
  due_date: string;
  amount: string;
  status: InstallmentStatus;
  is_overdue: boolean;
  paid_at: string | null;
  paid_amount: string | null;
  method: PaymentMethod | '';
  paid_note: string;
  settled_by_name: string;
  charge_kind: ChargeKind;
  has_active_charge: boolean;
  pix_code: string;
  pix_qr_base64: string;
  payment_url: string;
  charge_expires_at: string | null;
  last_reminder_on: string | null;
}

export interface FeeAgreement {
  id: string;
  client_id: string;
  client_name: string;
  legal_case_id: string | null;
  case_number: string;
  title: string;
  kind: AgreementKind;
  total_amount: string;
  status: AgreementStatus;
  notes: string;
  installments: Installment[];
  paid_total: string;
  open_total: string;
  created_at: string;
}

export interface AgreementInput {
  client_id: string;
  legal_case_id?: string | null;
  title: string;
  kind: AgreementKind;
  total_amount: string;
  installments_count: number;
  first_due: string;
  entry_amount?: string | null;
  notes?: string;
}

export interface FinanceSummary {
  month: string;
  received: string;
  expected: string;
  overdue_total: string;
  overdue_count: number;
  next_30_days: string;
  open_total: string;
}

export interface MercadoPagoStatus {
  connected: boolean;
  nickname: string;
  mp_user_id: string;
  can_manage: boolean;
  webhook_ready: boolean;
}

export const KIND_LABELS: Record<AgreementKind, string> = {
  CONTRATUAL: 'Honorários contratuais',
  EXITO: 'Honorários de êxito',
  MENSAL: 'Mensalidade / partido',
  CONSULTA: 'Consulta',
  OUTRO: 'Outro',
};

export const METHOD_LABELS: Record<PaymentMethod, string> = {
  PIX: 'Pix',
  BOLETO: 'Boleto',
  CARTAO: 'Cartão',
  TRANSFERENCIA: 'Transferência',
  DINHEIRO: 'Dinheiro',
  OUTRO: 'Outro',
};

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

export function money(value: string | number | null | undefined): string {
  return BRL.format(Number(value ?? 0));
}

/** "1.234,56" ou "1234.56" → "1234.56" (o backend recebe ponto). */
export function parseMoney(text: string): string | null {
  const clean = text.replace(/[^\d,.-]/g, '');
  if (!clean) return null;
  const normalized = clean.includes(',') ? clean.replace(/\./g, '').replace(',', '.') : clean;
  const value = Number(normalized);
  return Number.isFinite(value) && value > 0 ? value.toFixed(2) : null;
}

export function installmentState(i: Installment): { label: string; code: string } {
  // `code` casa com as cores do .badge global.
  if (i.status === 'PAID') return { label: 'Paga', code: 'PAID' };
  if (i.status === 'CANCELLED') return { label: 'Cancelada', code: 'ARCHIVED' };
  if (i.is_overdue) return { label: 'Atrasada', code: 'OVERDUE' };
  return { label: 'Em aberto', code: 'OPEN' };
}

/** Prévia do parcelamento (mesma regra do backend: centavos na 1ª parcela). */
export function previewPlan(
  total: string | null,
  count: number,
  firstDue: string,
  entry: string | null,
): { number: number; due: string; amount: number }[] {
  const totalCents = Math.round(Number(total ?? 0) * 100);
  const entryCents = entry ? Math.round(Number(entry) * 100) : 0;
  if (!totalCents || !count || !firstDue || entryCents >= totalCents) return [];
  const plan: { number: number; due: string; amount: number }[] = [];
  let offset = 0;
  if (entryCents) {
    plan.push({ number: 1, due: firstDue, amount: entryCents / 100 });
    offset = 1;
  }
  const rest = totalCents - entryCents;
  const base = Math.floor(rest / count);
  const leftover = rest - base * count;
  for (let i = 0; i < count; i++) {
    plan.push({
      number: plan.length + 1,
      due: addMonths(firstDue, i + offset),
      amount: (base + (i === 0 ? leftover : 0)) / 100,
    });
  }
  return plan;
}

export function addMonths(iso: string, months: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const index = m - 1 + months;
  const year = y + Math.floor(index / 12);
  const month = (index % 12) + 1;
  const last = new Date(year, month, 0).getDate();
  const day = Math.min(d, last);
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}
