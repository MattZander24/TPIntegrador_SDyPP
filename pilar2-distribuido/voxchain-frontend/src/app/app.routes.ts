import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: '/dashboard', pathMatch: 'full' },
  { path: 'dashboard', loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent) },
  { path: 'chain', loadComponent: () => import('./features/chain/chain.component').then(m => m.ChainComponent) },
  { path: 'laws', loadComponent: () => import('./features/laws/laws.component').then(m => m.LawsComponent) },
  { path: 'health', loadComponent: () => import('./features/health/health.component').then(m => m.HealthComponent) },
  { path: 'identity', loadComponent: () => import('./features/identity/identity.component').then(m => m.IdentityComponent) },
  { path: 'propose', loadComponent: () => import('./features/propose-law/propose-law.component').then(m => m.ProposeLawComponent) },
  { path: 'queue', loadComponent: () => import('./features/queue/queue.component').then(m => m.QueueComponent) },
  { path: '**', redirectTo: '/dashboard' }
];
