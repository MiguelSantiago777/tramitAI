import { Routes } from '@angular/router';

export const CLIENTES_ROUTES: Routes = [
  {
    path: '',
    title: 'Clientes · TramitAI',
    loadComponent: () => import('./client-list/client-list').then((m) => m.ClientList),
  },
  {
    path: 'novo',
    title: 'Novo cliente · TramitAI',
    loadComponent: () => import('./client-form/client-form').then((m) => m.ClientForm),
  },
  {
    path: ':id',
    title: 'Cliente · TramitAI',
    loadComponent: () => import('./client-form/client-form').then((m) => m.ClientForm),
  },
];
