import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

export const authGuard: CanMatchFn = () =>
  inject(AuthService).isAuthenticated() || inject(Router).createUrlTree(['/login']);

export const guestGuard: CanMatchFn = () =>
  !inject(AuthService).isAuthenticated() || inject(Router).createUrlTree(['/']);
