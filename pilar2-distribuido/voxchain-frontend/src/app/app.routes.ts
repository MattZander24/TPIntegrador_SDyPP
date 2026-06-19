import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: '/dashboard', pathMatch: 'full' },
  { path: 'dashboard', loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent) },
  { path: 'chain', loadComponent: () => import('./features/chain/chain.component').then(m => m.ChainComponent) },
  { path: 'laws', loadComponent: () => import('./features/laws/laws.component').then(m => m.LawsComponent) },
  { path: 'health', loadComponent: () => import('./features/health/health.component').then(m => m.HealthComponent) },
  { path: '**', redirectTo: '/dashboard' }
];
