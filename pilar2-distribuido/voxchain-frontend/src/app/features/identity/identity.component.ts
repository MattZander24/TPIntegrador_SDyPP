import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { IdentityService } from '../../core/services/identity.service';
import { AccountsService } from '../../core/services/accounts.service';

@Component({
  selector: 'app-identity',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule],
  template: `
    <div class="identity-container">
      <h1>Identity</h1>

      <mat-card *ngIf="!identityService.identity()">
        <mat-card-header>
          <mat-card-title>No Identity</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p>No account selected. Please select a demo account to participate in VoxChain governance.</p>
        </mat-card-content>
        <mat-card-actions>
          <button mat-raised-button color="primary" routerLink="/select-account">
            Select Account
          </button>
        </mat-card-actions>
      </mat-card>

      <mat-card *ngIf="identityService.identity() as id">
        <mat-card-header>
          <mat-card-title>Identity Active</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <div class="account-info" *ngIf="identityService.isDemoMode()">
            <p><strong>Account:</strong> <span class="account-name">{{ identityService.getUsername() }}</span></p>
            <p class="demo-badge">Demo Account</p>
          </div>
          <div class="key-display">
            <p><strong>Public Key:</strong></p>
            <code class="key-value">{{ id.pubkey.slice(0, 48) }}...</code>
          </div>
          <p class="note" *ngIf="identityService.isDemoMode()">
            Using pre-configured demo account for VoxChain governance.
          </p>
          <p class="note" *ngIf="!identityService.isDemoMode()">
            Use this identity to propose laws and participate in voting windows.
          </p>
        </mat-card-content>
        <mat-card-actions>
          <button mat-raised-button color="warn" (click)="clear()" *ngIf="!identityService.isDemoMode()">
            Clear Identity
          </button>
          <button mat-button color="primary" (click)="changeAccount()" *ngIf="identityService.isDemoMode()">
            Change Account
          </button>
        </mat-card-actions>
      </mat-card>
    </div>
  `,
  styles: [`
    .identity-container {
      padding: 20px;
      max-width: 800px;
      margin: 0 auto;
    }
    h1 { color: #e0e0e0; }
    mat-card {
      background-color: #1e1e1e;
      color: #e0e0e0;
    }
    mat-card-title { color: #e0e0e0; }
    .hint, .note {
      color: #888;
      font-size: 0.9rem;
    }
    .account-info {
      margin: 16px 0;
      padding: 12px;
      background-color: #2a2a2a;
      border-radius: 4px;
    }
    .account-name {
      color: #64b5f6;
      font-weight: 600;
      font-size: 1.1rem;
    }
    .demo-badge {
      color: #4caf50;
      font-weight: 600;
      margin-top: 8px;
    }
    .key-display {
      margin: 16px 0;
    }
    .key-value {
      font-family: 'Courier New', monospace;
      font-size: 0.8rem;
      background-color: #2a2a2a;
      padding: 8px 12px;
      border-radius: 4px;
      display: block;
      word-break: break-all;
      color: #64b5f6;
    }
  `]
})
export class IdentityComponent {
  identityService = inject(IdentityService);
  accountsService = inject(AccountsService);
  router = inject(Router);
  generating = signal(false);

  async generate() {
    this.generating.set(true);
    try {
      await this.identityService.generateKeypair();
    } finally {
      this.generating.set(false);
    }
  }

  clear() {
    this.identityService.clearIdentity();
  }

  changeAccount() {
    this.accountsService.clearSession();
    this.identityService.clearIdentity();
    this.router.navigate(['/select-account']);
  }
}
