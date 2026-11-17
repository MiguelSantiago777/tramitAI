import { HttpParams } from '@angular/common/http';

/** Resposta paginada do DRF. */
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Monta HttpParams ignorando vazios. `pageIndex` é 0-based (MatPaginator); a API é 1-based. */
export function listParams(
  filters: Record<string, string | null | undefined>,
  pageIndex = 0,
  pageSize = 25,
): HttpParams {
  let params = new HttpParams().set('page', pageIndex + 1).set('page_size', pageSize);
  for (const [key, value] of Object.entries(filters)) {
    if (value) {
      params = params.set(key, value);
    }
  }
  return params;
}
