import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type TrashKind = 'client' | 'case';

export interface TrashItem {
  kind: TrashKind;
  id: string;
  label: string;
  detail: string;
  deleted_at: string;
  deleted_by_name: string;
  /** Quando será apagado de vez. */
  purge_at: string;
}

/** Remover cliente/processo (vai para a Lixeira), restaurar e apagar de vez. */
@Injectable({ providedIn: 'root' })
export class TrashService {
  private readonly http = inject(HttpClient);

  list(): Observable<TrashItem[]> {
    return this.http.get<TrashItem[]>('/api/v1/trash/');
  }

  /** Manda para a Lixeira. `force` confirma cliente com parcelas em aberto. */
  remove(kind: TrashKind, id: string, force = false): Observable<void> {
    const base = kind === 'client' ? '/api/v1/clients/' : '/api/v1/cases/';
    const params = force ? new HttpParams().set('force', '1') : undefined;
    return this.http.delete<void>(`${base}${id}/`, { params });
  }

  restore(kind: TrashKind, id: string): Observable<void> {
    return this.http.post<void>(`/api/v1/trash/${kind}/${id}/restore/`, {});
  }

  purge(kind: TrashKind, id: string): Observable<void> {
    return this.http.delete<void>(`/api/v1/trash/${kind}/${id}/`);
  }
}
