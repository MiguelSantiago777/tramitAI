import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';

import { AUTH_URLS, AuthService } from './auth.service';

const withToken = (req: HttpRequest<unknown>, token: string | null) =>
  token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

/** Põe o Bearer nas chamadas /api e tenta um refresh quando o access expira (401). */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const isPublic = req.url === AUTH_URLS.login || req.url === AUTH_URLS.refresh;
  if (!req.url.startsWith('/api/') || isPublic) {
    return next(req);
  }

  const auth = inject(AuthService);
  const router = inject(Router);

  return next(withToken(req, auth.accessToken)).pipe(
    catchError((err: unknown) => {
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
