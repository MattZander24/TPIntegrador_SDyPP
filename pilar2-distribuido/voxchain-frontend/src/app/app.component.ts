import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { RouterModule } from '@angular/router';
import { IdentityService } from './core/services/identity.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, MatToolbarModule, MatButtonModule, RouterModule],
  template: `
    <mat-toolbar color="primary">
      <span>VoxChain</span>
      <span class="spacer"></span>
      <a mat-button routerLink="/dashboard">Dashboard</a>
      <a mat-button routerLink="/chain">Chain</a>
      <a mat-button routerLink="/laws">Laws</a>
      <a mat-button routerLink="/health">Health</a>
      <a mat-button routerLink="/workers">Workers</a>
      <a mat-button routerLink="/queue" *ngIf="identityService.identity()">Vote</a>
      <a mat-button routerLink="/propose" *ngIf="identityService.identity()">Propose Law</a>
      <a mat-button routerLink="/identity" *ngIf="!identityService.identity()">Register</a>
      <span *ngIf="identityService.identity() as id" class="identity-badge">
        {{ identityService.getPubkeyShort() }}
      </span>
    </mat-toolbar>
    <router-outlet></router-outlet>
  `,
  styles: [`
    :host {
      display: block;
      height: 100vh;
    }
    .spacer {
      flex: 1 1 auto;
    }
    mat-toolbar {
      margin-bottom: 20px;
    }
    a {
      color: white;
      text-decoration: none;
    }
    a.mat-button {
      margin-left: 10px;
    }
    .identity-badge {
      font-size: 0.75rem;
      color: #90caf9;
      background-color: rgba(255,255,255,0.1);
      padding: 4px 8px;
      border-radius: 12px;
      margin-left: 10px;
    }
  `]
})
export class AppComponent {
  identityService = inject(IdentityService);
}
