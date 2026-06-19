import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-health',
  standalone: true,
  imports: [CommonModule, MatCardModule],
  template: `
    <div class="health-container">
      <h1>Health Status</h1>
      
      <div class="health-cards">
        <mat-card [class.status-ok]="health().api === 'ok'" [class.status-error]="health().api !== 'ok'">
          <mat-card-header>
            <mat-card-title>API</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="status">{{ health().api }}</p>
          </mat-card-content>
        </mat-card>

        <mat-card [class.status-ok]="health().nct === 'ok'" [class.status-error]="health().nct !== 'ok'">
          <mat-card-header>
            <mat-card-title>NCT</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="status">{{ health().nct }}</p>
          </mat-card-content>
        </mat-card>

        <mat-card [class.status-ok]="health().trp === 'ok'" [class.status-error]="health().trp !== 'ok'">
          <mat-card-header>
            <mat-card-title>Transaction Pool</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="status">{{ health().trp }}</p>
          </mat-card-content>
        </mat-card>

        <mat-card [class.status-ok]="health().redis === 'ok'" [class.status-error]="health().redis !== 'ok'">
          <mat-card-header>
            <mat-card-title>Redis</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="status">{{ health().redis }}</p>
          </mat-card-content>
        </mat-card>
      </div>
    </div>
  `,
  styles: [`
    .health-container {
      padding: 20px;
      max-width: 1400px;
      margin: 0 auto;
    }
    h1 {
      color: #e0e0e0;
    }
    .health-cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 20px;
    }
    mat-card {
      background-color: #1e1e1e;
      color: #e0e0e0;
    }
    mat-card-title {
      color: #e0e0e0;
    }
    .status {
      font-size: 1.5rem;
      font-weight: bold;
      margin: 0;
    }
    .status-ok .status {
      color: #4caf50;
    }
    .status-error .status {
      color: #f44336;
    }
  `]
})
export class HealthComponent implements OnInit {
  private apiService = inject(ApiService);
  health = signal<any>({ api: 'loading', nct: 'loading', trp: 'loading', redis: 'loading' });

  ngOnInit() {
    this.loadHealth();
    // Poll every 10 seconds
    setInterval(() => this.loadHealth(), 10000);
  }

  private loadHealth() {
    this.apiService.getHealth().subscribe((status: any) => {
      this.health.set(status);
    });
  }
}
