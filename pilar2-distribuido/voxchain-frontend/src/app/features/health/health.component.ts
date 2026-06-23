import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
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

        <mat-card [class.status-ok]="health().workers === 'ok'" [class.status-error]="health().workers !== 'ok'">
          <mat-card-header>
            <mat-card-title>Workers</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="status">{{ health().workers }}</p>
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
export class HealthComponent implements OnInit, OnDestroy {
  private apiService = inject(ApiService);
  health = signal<any>({ api: 'loading', nct: 'loading', workers: 'loading', redis: 'loading' });
  private healthInterval: ReturnType<typeof setInterval> | null = null;

  ngOnInit() {
    this.loadHealth();
    this.healthInterval = setInterval(() => this.loadHealth(), 10000);
  }

  ngOnDestroy() {
    if (this.healthInterval) {
      clearInterval(this.healthInterval);
      this.healthInterval = null;
    }
  }

  private loadHealth() {
    this.apiService.getHealth().subscribe((status: any) => {
      this.health.set(status);
    });
  }
}
