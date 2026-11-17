export type Stage = 'NEW' | 'TRIAGE' | 'CONSULT' | 'PROPOSAL' | 'WON' | 'LOST';
export type Area =
  | 'TRABALHISTA'
  | 'PREVIDENCIARIO'
  | 'FAMILIA'
  | 'CONSUMIDOR'
  | 'CIVEL'
  | 'CRIMINAL'
  | 'IMOBILIARIO'
  | 'TRIBUTARIO'
  | 'OUTRA';
export type Source = 'WHATSAPP' | 'INDICACAO' | 'REDES' | 'SITE' | 'PRESENCIAL' | 'OUTRA';

export interface Opportunity {
  id: string;
  title: string;
  client_id: string;
  client_name: string;
  client_phone: string;
  client_status: string;
  stage: Stage;
  area: Area | '';
  source: Source;
  estimated_value: string | null;
  owner_id: string | null;
  owner_name: string;
  conversation_id: string | null;
  notes: string;
  lost_reason: string;
  position: number;
  stage_changed_at: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface OpportunityInput {
  title?: string;
  client_id?: string | null;
  new_client_name?: string;
  new_client_phone?: string;
  area?: Area | '';
  source?: Source;
  estimated_value?: string | null;
  owner_id?: string | null;
  notes?: string;
}

export interface BoardSummary {
  open_count: number;
  by_stage: Record<string, number>;
  open_value: string;
  won_count: number;
  lost_count: number;
  won_value: string;
  conversion_rate: number | null;
  period_days: number;
}

export const STAGES: { id: Stage; label: string; hint: string }[] = [
  { id: 'NEW', label: 'Novo contato', hint: 'Chegou e ainda ninguém falou' },
  { id: 'TRIAGE', label: 'Em triagem', hint: 'Entendendo o caso' },
  { id: 'CONSULT', label: 'Consulta marcada', hint: 'Atendimento agendado' },
  { id: 'PROPOSAL', label: 'Proposta enviada', hint: 'Aguardando resposta' },
  { id: 'WON', label: 'Contratou', hint: 'Últimos 30 dias' },
  { id: 'LOST', label: 'Não contratou', hint: 'Últimos 30 dias' },
];

export const AREA_LABELS: Record<Area, string> = {
  TRABALHISTA: 'Trabalhista',
  PREVIDENCIARIO: 'Previdenciário',
  FAMILIA: 'Família',
  CONSUMIDOR: 'Consumidor',
  CIVEL: 'Cível',
  CRIMINAL: 'Criminal',
  IMOBILIARIO: 'Imobiliário',
  TRIBUTARIO: 'Tributário',
  OUTRA: 'Outra',
};

export const SOURCE_LABELS: Record<Source, string> = {
  WHATSAPP: 'WhatsApp',
  INDICACAO: 'Indicação',
  REDES: 'Redes sociais',
  SITE: 'Site / Google',
  PRESENCIAL: 'Presencial',
  OUTRA: 'Outra',
};

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  maximumFractionDigits: 0,
});

export function money(value: string | number | null | undefined): string {
  const n = typeof value === 'string' ? Number(value) : (value ?? 0);
  return BRL.format(Number.isFinite(n) ? n : 0);
}
