export type TaskKind = 'TASK' | 'DEADLINE' | 'FOLLOW_UP';
export type TaskStatus = 'OPEN' | 'DONE' | 'CANCELED';
export type TaskPriority = 'LOW' | 'NORMAL' | 'HIGH';
export type EventKind = 'HEARING' | 'MEETING' | 'CONSULT' | 'OTHER';
export type EventStatus = 'PENDING' | 'SCHEDULED' | 'DONE' | 'CANCELED';

export interface Task {
  id: string;
  title: string;
  description: string;
  kind: TaskKind;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  due_time: string | null;
  assignee_id: string | null;
  assignee_name: string;
  client_id: string | null;
  client_name: string;
  legal_case_id: string | null;
  case_number: string;
  source: 'MANUAL' | 'MOVEMENT';
  completed_at: string | null;
  completed_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface TaskInput {
  title: string;
  description: string;
  kind: TaskKind;
  priority: TaskPriority;
  status?: TaskStatus;
  due_date: string | null;
  due_time: string | null;
  assignee_id: string | null;
  client_id: string | null;
  legal_case_id: string | null;
}

export interface CalendarEvent {
  id: string;
  title: string;
  kind: EventKind;
  status: EventStatus;
  starts_at: string;
  ends_at: string | null;
  location: string;
  notes: string;
  responsible_id: string | null;
  responsible_name: string;
  client_id: string | null;
  client_name: string;
  legal_case_id: string | null;
  case_number: string;
  remind_client: boolean;
  client_reminded_at: string | null;
  created_at: string;
  updated_at: string;
}

export type EventInput = Pick<
  CalendarEvent,
  | 'title'
  | 'kind'
  | 'starts_at'
  | 'ends_at'
  | 'location'
  | 'notes'
  | 'responsible_id'
  | 'client_id'
  | 'legal_case_id'
  | 'remind_client'
> & { status?: EventStatus };

export interface Desk {
  overdue: Task[];
  today: Task[];
  upcoming: Task[];
  no_date: Task[];
  events_today: CalendarEvent[];
  events_upcoming: CalendarEvent[];
}

export const TASK_KIND_LABELS: Record<TaskKind, string> = {
  TASK: 'Tarefa',
  DEADLINE: 'Prazo',
  FOLLOW_UP: 'Retorno ao cliente',
};

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  LOW: 'Baixa',
  NORMAL: 'Normal',
  HIGH: 'Alta',
};

export const EVENT_KIND_LABELS: Record<EventKind, string> = {
  HEARING: 'Audiência',
  MEETING: 'Reunião',
  CONSULT: 'Atendimento',
  OTHER: 'Outro',
};

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  PENDING: 'A confirmar',
  SCHEDULED: 'Agendado',
  DONE: 'Realizado',
  CANCELED: 'Cancelado',
};

/** "2026-11-17" do dia local (sem converter para UTC). */
export function isoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function todayIso(): string {
  return isoDate(new Date());
}

export function isOverdue(task: Task): boolean {
  return task.status === 'OPEN' && !!task.due_date && task.due_date < todayIso();
}
