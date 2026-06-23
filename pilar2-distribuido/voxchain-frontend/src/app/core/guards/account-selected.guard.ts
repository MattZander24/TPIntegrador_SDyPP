import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AccountsService } from '../services/accounts.service';

export const accountSelectedGuard: CanActivateFn = () => {
  const accountsService = inject(AccountsService);
  const router = inject(Router);
  
  if (accountsService.selectedAccount()) {
    return true;
  }
  
  router.navigate(['/select-account']);
  return false;
};
