export type Role = 'OWNER' | 'LAWYER' | 'STAFF';

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: 'ACTIVE' | 'SUSPENDED';
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  oab_number: string;
}

export interface Session {
  user: User;
  tenant: Tenant;
  role: Role;
  can_approve: boolean;
  /** Dono do TramitAI: vê o Painel da plataforma. */
  is_platform_admin?: boolean;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  session: Session;
}

/** Item de `details.tenants` quando o login responde `tenant_selection_required`. */
export interface TenantOption {
  id: string;
  name: string;
}

export const ROLE_LABELS: Record<Role, string> = {
  OWNER: 'Titular',
  LAWYER: 'Advogado(a)',
  STAFF: 'Equipe',
};
