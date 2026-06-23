import { Routes } from '@angular/router';
import { accountSelectedGuard } from './core/guards/account-selected.guard';

export const routes: Routes = [
  { path: '', redirectTo: '/select-account', pathMatch: 'full' },
  { 
    path: 'select-account', 
    loadComponent: () => import('./features/account-selection/account-selection.component').then(m => m.AccountSelectionComponent) 
  },
  { 
    path: 'dashboard', 
    loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
    canActivate: [accountSelectedGuard]
  },
  { 
    path: 'chain', 
    loadComponent: () => import('./features/chain/chain.component').then(m => m.ChainComponent),
    canActivate: [accountSelectedGuard]
  },
  { 
    path: 'laws', 
    loadComponent: () => import('./features/laws/laws.component').then(m => m.LawsComponent),
    canActivate: [accountSelectedGuard]
  },
  { 
    path: 'health', 
    loadComponent: () => import('./features/health/health.component').then(m => m.HealthComponent),
    canActivate: [accountSelectedGuard]
  },
  { 
    path: 'identity', 
    loadComponent: () => import('./features/identity/identity.component').then(m => m.IdentityComponent),
    canActivate: [accountSelectedGuard]
  },
  { 
    path: 'propose', 
    loadComponent: () => import('./features/propose-law/propose-law.component').then(m => m.ProposeLawComponent),
    canActivate: [accountSelectedGuard]
  },
  { 
    path: 'queue', 
    loadComponent: () => import('./features/queue/queue.component').then(m => m.QueueComponent),
    canActivate: [accountSelectedGuard]
  },
  { 
    path: 'workers', 
    loadComponent: () => import('./features/workers/workers.component').then(m => m.WorkersComponent),
    canActivate: [accountSelectedGuard]
  },
  { path: '**', redirectTo: '/select-account' }
];
