import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { IdentityService } from '../../core/services/identity.service';

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
          <p>Generate a keypair to participate in VoxChain governance.</p>
          <p class="hint">Your private key is stored locally and never sent to the server.</p>
        </mat-card-content>
        <mat-card-actions>
          <button mat-raised-button color="primary" (click)="generate()" [disabled]="generating()">
            {{ generating() ? 'Generating...' : 'Generate Keypair' }}
          </button>
        </mat-card-actions>
      </mat-card>

      <mat-card *ngIf="identityService.identity() as id">
        <mat-card-header>
          <mat-card-title>Identity Active</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <div class="key-display">
            <p><strong>Public Key:</strong></p>
            <code class="key-value">{{ id.pubkey.slice(0, 48) }}...</code>
          </div>
          <p class="note">Use this identity to propose laws and participate in voting windows.</p>
        </mat-card-content>
        <mat-card-actions>
          <button mat-raised-button color="warn" (click)="clear()">Clear Identity</button>
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
}
