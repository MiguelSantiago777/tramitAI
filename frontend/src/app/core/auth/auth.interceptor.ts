import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';

import { AUTH_URLS, AuthService } from './auth.service';

const withToken = (req: HttpRequest<unknown>, token: string | null) =>
  token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

/** Põe o Bearer nas chamadas /api e tenta um refresh quando o access expira (401). */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const publicUrls: string[] = [AUTH_URLS.login, AUTH_URLS.refresh, AUTH_URLS.signup];
  const isPublic = publicUrls.includes(req.url);
  if (!req.url.startsWith('/api/') || isPublic) {
    return next(req);
  }

  const auth = inject(AuthService);
  const router = inject(Router);

  return next(withToken(req, auth.accessToken)).pipe(
    catchError((err: unknown) => {
      // Assinatura vencida: leva para a página de assinatura (o resto da API fica fechado).
      if (err instanceof HttpErrorResponse && err.status === 402) {
        if (!router.url.startsWith('/assinatura')) void router.navigate(['/assinatura']);
        return throwError(() => err);
      }
      if (!(err instanceof HttpErrorResponse) || err.status !== 401 || !auth.hasRefreshToken) {
        return throwError(() => err);
      }
      return auth.refresh().pipe(
        switchMap((token) => next(withToken(req, token))),
        catchError((refreshErr: unknown) => {
          auth.logout();
          void router.navigate(['/login']);
          return throwError(() => refreshErr);
        }),
      );
    }),
  );
};
