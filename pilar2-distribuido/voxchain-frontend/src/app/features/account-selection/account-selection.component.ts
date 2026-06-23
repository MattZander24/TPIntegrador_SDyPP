import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { AccountsService, DemoAccount } from '../../core/services/accounts.service';
import { IdentityService } from '../../core/services/identity.service';

@Component({
  selector: 'app-account-selection',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule
  ],
  template: `
    <div class="account-selection-container">
      <h1>Select Demo Account</h1>
      <p class="subtitle">Choose one of the 5 pre-configured demo accounts to access VoxChain</p>

      <div class="accounts-grid" *ngIf="!loading()">
        <mat-card 
          *ngFor="let account of accounts()" 
          class="account-card"
          [class.available]="account.status === 'available'"
          [class.occupied]="account.status === 'occupied'"
          [class.selected]="selectedAccount()?.username === account.username">
          <mat-card-header>
            <mat-card-title>
              <span class="username">{{ account.username }}</span>
              <span class="status-badge" [class.available]="account.status === 'available'">
                {{ account.status === 'available' ? 'Available' : 'In Use' }}
              </span>
            </mat-card-title>
            <mat-card-subtitle>{{ account.worker_id }}</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <div class="account-details">
              <p><strong>Mode:</strong> {{ account.mode }}</p>
              <p><strong>Public Key:</strong> <code class="pubkey">{{ account.pubkey.slice(0, 32) }}...</code></p>
              <p *ngIf="account.status === 'occupied'" class="occupied-info">
                Occupied since: {{ formatTime(account.occupied_at) }}
              </p>
            </div>
          </mat-card-content>
          <mat-card-actions>
            <button 
              mat-raised-button 
              [color]="account.status === 'available' ? 'primary' : 'warn'"
              (click)="selectAccount(account)"
              [disabled]="account.status === 'occupied' && selectedAccount()?.username !== account.username">
              {{ getButtonText(account) }}
            </button>
            <button 
              mat-button 
              *ngIf="selectedAccount()?.username === account.username"
              (click)="releaseAccount(account)">
              Release
            </button>
          </mat-card-actions>
        </mat-card>
      </div>

      <div class="loading-container" *ngIf="loading()">
        <mat-spinner></mat-spinner>
        <p>Loading accounts...</p>
      </div>
    </div>
  `,
  styles: [`
    .account-selection-container {
      padding: 40px 20px;
      max-width: 1200px;
      margin: 0 auto;
      text-align: center;
    }
    h1 {
      color: #e0e0e0;
      margin-bottom: 8px;
    }
    .subtitle {
      color: #888;
      margin-bottom: 40px;
      font-size: 1.1rem;
    }
    .accounts-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 24px;
      text-align: left;
    }
    .account-card {
      background-color: #1e1e1e;
      color: #e0e0e0;
      border: 2px solid transparent;
      transition: all 0.3s ease;
    }
    .account-card.available {
      border-color: #4caf50;
    }
    .account-card.occupied {
      border-color: #f44336;
      opacity: 0.7;
    }
    .account-card.selected {
      border-color: #2196f3;
      box-shadow: 0 0 20px rgba(33, 150, 243, 0.3);
    }
    .account-card:hover:not(.occupied) {
      transform: translateY(-4px);
      box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3);
    }
    mat-card-title {
      color: #e0e0e0;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .username {
      font-size: 1.3rem;
      font-weight: 600;
    }
    .status-badge {
      font-size: 0.75rem;
      padding: 4px 12px;
      border-radius: 12px;
      background-color: #f44336;
      color: white;
      font-weight: 600;
    }
    .status-badge.available {
      background-color: #4caf50;
    }
    mat-card-subtitle {
      color: #888;
    }
    .account-details {
      margin: 16px 0;
    }
    .account-details p {
      margin: 8px 0;
      color: #b0b0b0;
    }
    .account-details strong {
      color: #e0e0e0;
    }
    .pubkey {
      font-family: 'Courier New', monospace;
      font-size: 0.8rem;
      background-color: #2a2a2a;
      padding: 4px 8px;
      border-radius: 4px;
      color: #64b5f6;
    }
    .occupied-info {
      color: #f44336;
      font-size: 0.9rem;
    }
    mat-card-actions {
      display: flex;
      gap: 8px;
    }
    .loading-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 16px;
      color: #888;
    }
  `]
})
export class AccountSelectionComponent implements OnInit {
  accountsService = inject(AccountsService);
  router = inject(Router);
  snackBar = inject(MatSnackBar);
  identityService = inject(IdentityService);

  accounts = signal<DemoAccount[]>([]);
  loading = signal(true);
  selectedAccount = signal<DemoAccount | null>(null);

  ngOnInit() {
    this.loadAccounts();
    
    // Check if already has a selected account
    const saved = this.accountsService.selectedAccount();
    if (saved) {
      this.selectedAccount.set(saved);
    }
  }

  loadAccounts() {
    this.loading.set(true);
    this.accountsService.listAccounts().subscribe({
      next: (accounts) => {
        this.accounts.set(accounts);
        this.loading.set(false);
      },
      error: (err) => {
        console.error('Failed to load accounts:', err);
        this.snackBar.open('Failed to load accounts. Retrying...', 'Close', { duration: 3000 });
        setTimeout(() => this.loadAccounts(), 3000);
      }
    });
  }

  async selectAccount(account: DemoAccount) {
    if (account.status === 'occupied') {
      this.snackBar.open('This account is already in use by another session', 'Close', { duration: 3000 });
      return;
    }

    try {
      const response = await this.accountsService.reserveAccount(account.username).toPromise();
      
      if (response?.status === 'reserved' || response?.status === 'already_reserved') {
        this.accountsService.setSelectedAccount(account);
        this.selectedAccount.set(account);
        
        // Update identity service with the demo account's pubkey
        this.identityService.identity.set({
          pubkey: account.pubkey,
          exportedPrivkey: null,
          username: account.username,
          isDemo: true
        });
        
        this.snackBar.open(`Account "${account.username}" selected successfully`, 'Close', { duration: 2000 });
        
        // Reload accounts to update status
        this.loadAccounts();
        
        // Navigate to dashboard after short delay
        setTimeout(() => {
          this.router.navigate(['/dashboard']);
        }, 500);
      }
    } catch (error: any) {
      console.error('Failed to reserve account:', error);
      if (error.status === 409) {
        this.snackBar.open('This account is already in use by another session', 'Close', { duration: 3000 });
        this.loadAccounts();
      } else {
        this.snackBar.open('Failed to select account. Please try again.', 'Close', { duration: 3000 });
      }
    }
  }

  async releaseAccount(account: DemoAccount) {
    try {
      const response = await this.accountsService.releaseAccount(account.username).toPromise();
      
      if (response?.status === 'released') {
        this.accountsService.setSelectedAccount(null);
        this.selectedAccount.set(null);
        this.snackBar.open(`Account "${account.username}" released`, 'Close', { duration: 2000 });
        this.loadAccounts();
      }
    } catch (error: any) {
      console.error('Failed to release account:', error);
      this.snackBar.open('Failed to release account. Please try again.', 'Close', { duration: 3000 });
    }
  }

  getButtonText(account: DemoAccount): string {
    if (this.selectedAccount()?.username === account.username) {
      return 'Selected';
    }
    if (account.status === 'occupied') {
      return 'In Use';
    }
    return 'Select';
  }

  formatTime(isoString?: string): string {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleTimeString();
  }
}
