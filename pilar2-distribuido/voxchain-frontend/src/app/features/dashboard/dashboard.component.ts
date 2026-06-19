import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { ApiService } from '../../core/services/api.service';
import { EventsService } from '../../core/services/events.service';
import { Block } from '../../core/models/block.model';
import { Law } from '../../core/models/law.model';
import { Window } from '../../core/models/window.model';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule],
  template: `
    <div class="dashboard-container">
      <h1>Dashboard</h1>
      
      <div class="metrics">
        <mat-card>
          <mat-card-header>
            <mat-card-title>Total Blocks</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="metric-value">{{ chainLength() }}</p>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-header>
            <mat-card-title>Promulgated Laws</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="metric-value">{{ promulgatedLaws() }}</p>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-header>
            <mat-card-title>Pending Laws</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="metric-value">{{ pendingLaws() }}</p>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-header>
            <mat-card-title>Active Window</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p class="metric-value">{{ activeWindow() ? 'Yes' : 'No' }}</p>
          </mat-card-content>
        </mat-card>
      </div>

      <div class="recent-activity">
        <h2>Recent Activity</h2>
        <mat-card *ngIf="recentBlocks().length > 0">
          <mat-card-content>
            <div class="block-item" *ngFor="let block of recentBlocks()">
              <p><strong>Block:</strong> {{ block.block_hash.slice(0, 12) }}...</p>
              <p><strong>Law:</strong> {{ block.law_id }}</p>
              <p><strong>Action:</strong> {{ block.action }}</p>
              <p><strong>Timestamp:</strong> {{ block.timestamp }}</p>
            </div>
          </mat-card-content>
        </mat-card>
        <p *ngIf="recentBlocks().length === 0">No recent activity</p>
      </div>
    </div>
  `,
  styles: [`
    .dashboard-container {
      padding: 20px;
      max-width: 1400px;
      margin: 0 auto;
    }
    h1 {
      color: #e0e0e0;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 20px;
      margin-bottom: 30px;
    }
    .metric-value {
      font-size: 2rem;
      font-weight: bold;
      color: #64b5f6;
      margin: 0;
    }
    .recent-activity {
      margin-top: 30px;
    }
    .recent-activity h2 {
      color: #e0e0e0;
    }
    .block-item {
      padding: 10px 0;
      border-bottom: 1px solid #333;
    }
    .block-item:last-child {
      border-bottom: none;
    }
    .block-item p {
      margin: 5px 0;
      color: #b0b0b0;
    }
    mat-card {
      background-color: #1e1e1e;
      color: #e0e0e0;
    }
    mat-card-title {
      color: #e0e0e0;
    }
  `]
})
export class DashboardComponent implements OnInit {
  private apiService = inject(ApiService);
  private eventsService = inject(EventsService);

  chainLength = signal(0);
  promulgatedLaws = signal(0);
  pendingLaws = signal(0);
  activeWindow = signal<Window | null>(null);
  recentBlocks = signal<Block[]>([]);

  ngOnInit() {
    this.loadMetrics();
  }

  private loadMetrics() {
    this.apiService.getChain().subscribe((blocks: Block[]) => {
      this.chainLength.set(blocks.length);
      this.recentBlocks.set(blocks.slice(-5).reverse());
      
      const promulgated = blocks.filter((b: Block) => b.action === 'promulgacion').length;
      this.promulgatedLaws.set(promulgated);
    });

    this.apiService.getLaws().subscribe((laws: Law[]) => {
      const pending = laws.filter((l: Law) => l.status === 'pending_queue').length;
      this.pendingLaws.set(pending);
    });

    this.apiService.getActiveWindow().subscribe({
      next: (window: Window | null) => this.activeWindow.set(window),
      error: () => this.activeWindow.set(null)
    });
  }

}
