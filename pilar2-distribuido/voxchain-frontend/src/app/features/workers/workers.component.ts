import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/services/api.service';

interface WorkerStatus {
  worker_id: string;
  mode: string;
  pool_url: string;
  running: boolean;
}

interface PoolPolicy {
  decision: string;
  action?: string;
}

interface PoolHealth {
  pool: string;
  rabbitmq: string;
  miners: number;
  voting_policy: PoolPolicy;
}

@Component({
  selector: 'app-workers',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatSelectModule,
    MatFormFieldModule,
    MatInputModule,
    MatTableModule,
    MatIconModule,
  ],
  template: `
    <div class="workers-container">
      <h1>Workers Management</h1>
      
      <mat-card class="workers-card">
        <mat-card-header>
          <mat-card-title>Worker Status</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <div class="table-container">
            <table mat-table [dataSource]="workers()">
              <ng-container matColumnDef="worker_id">
                <th mat-header-cell *matHeaderCellDef>Worker ID</th>
                <td mat-cell *matCellDef="let worker">{{ worker.worker_id }}</td>
              </ng-container>

              <ng-container matColumnDef="mode">
                <th mat-header-cell *matHeaderCellDef>Mode</th>
                <td mat-cell *matCellDef="let worker">
                  <span [class.mode-badge]="true" [class.mode-standalone]="worker.mode === 'standalone'" 
                        [class.mode-pool-coordinator]="worker.mode === 'pool-coordinator'"
                        [class.mode-pool-worker]="worker.mode === 'pool-worker'">
                    {{ worker.mode }}
                  </span>
                </td>
              </ng-container>

              <ng-container matColumnDef="pool_url">
                <th mat-header-cell *matHeaderCellDef>Pool URL</th>
                <td mat-cell *matCellDef="let worker">{{ worker.pool_url || '-' }}</td>
              </ng-container>

              <ng-container matColumnDef="policy">
                <th mat-header-cell *matHeaderCellDef>Policy</th>
                <td mat-cell *matCellDef="let worker">
                  <span [class.policy-badge]="true" [class.policy-accept]="getPolicyDisplay(worker) === 'Accept All'"
                        [class.policy-reject]="getPolicyDisplay(worker).startsWith('Reject')">
                    {{ getPolicyDisplay(worker) }}
                  </span>
                </td>
              </ng-container>

              <ng-container matColumnDef="running">
                <th mat-header-cell *matHeaderCellDef>Running</th>
                <td mat-cell *matCellDef="let worker">
                  <span [class.running-text]="worker.running" [class.stopped-text]="!worker.running">
                    {{ worker.running ? 'Running' : 'Stopped' }}
                  </span>
                </td>
              </ng-container>

              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef>Actions</th>
                <td mat-cell *matCellDef="let worker">
                  <button mat-button (click)="openSwitchDialog(worker)" [disabled]="!worker.running">
                    Switch Mode
                  </button>
                  <button mat-button (click)="openPolicyDialog(worker)" *ngIf="worker.mode === 'pool-coordinator'">
                    Configure Policy
                  </button>
                </td>
              </ng-container>

              <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
              <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
            </table>
          </div>
        </mat-card-content>
      </mat-card>

      <mat-card class="switch-card" *ngIf="selectedWorker()">
        <mat-card-header>
          <mat-card-title>Switch Worker Mode</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p><strong>Worker:</strong> {{ selectedWorker()?.worker_id }}</p>
          <p><strong>Current Mode:</strong> {{ selectedWorker()?.mode }}</p>

          <div class="form-field">
            <mat-form-field appearance="fill">
              <mat-label>Target Mode</mat-label>
              <mat-select [(value)]="targetMode">
                <mat-option value="standalone">Standalone</mat-option>
                <mat-option value="pool-coordinator">Pool Coordinator</mat-option>
                <mat-option value="pool-worker">Pool Worker</mat-option>
              </mat-select>
            </mat-form-field>
          </div>

          <div class="form-field" *ngIf="targetMode() === 'pool-worker'">
            <mat-form-field appearance="fill">
              <mat-label>Pool Coordinator URL</mat-label>
              <input matInput [(ngModel)]="poolUrl" placeholder="http://pool-coordinator:9001">
            </mat-form-field>
          </div>

          <div class="actions">
            <button mat-button (click)="cancelSwitch()">Cancel</button>
            <button mat-raised-button color="primary" (click)="confirmSwitch()" [disabled]="!canSwitch()">
              Switch Mode
            </button>
          </div>
        </mat-card-content>
      </mat-card>

      <mat-card class="policy-card" *ngIf="selectedPoolCoordinator()">
        <mat-card-header>
          <mat-card-title>Configure Pool Voting Policy</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p><strong>Pool Coordinator:</strong> {{ selectedPoolCoordinator()?.worker_id }}</p>
          <div *ngIf="poolHealth()">
            <p><strong>Miners Connected:</strong> {{ poolHealth()?.miners }}</p>
            <p><strong>Current Policy:</strong> {{ poolHealth()?.voting_policy?.decision }}</p>
          </div>

          <div class="form-field">
            <mat-form-field appearance="fill">
              <mat-label>Decision</mat-label>
              <mat-select [(value)]="policyDecision">
                <mat-option value="accept">Accept All</mat-option>
                <mat-option value="reject">Reject Specific</mat-option>
              </mat-select>
            </mat-form-field>
          </div>

          <div class="form-field" *ngIf="policyDecision() === 'reject'">
            <mat-form-field appearance="fill">
              <mat-label>Action to Reject</mat-label>
              <mat-select [(value)]="policyAction">
                <mat-option value="promulgacion">Promulgación</mat-option>
                <mat-option value="derogacion">Derogación</mat-option>
                <mat-option value="">Reject All</mat-option>
              </mat-select>
            </mat-form-field>
          </div>

          <div class="actions">
            <button mat-button (click)="cancelPolicy()">Cancel</button>
            <button mat-raised-button color="primary" (click)="confirmPolicy()">
              Update Policy
            </button>
          </div>
        </mat-card-content>
      </mat-card>

      <div class="info-section">
        <h3>Worker Modes</h3>
        <ul>
          <li><strong>Standalone:</strong> Worker mines independently by subscribing to NCT challenges</li>
          <li><strong>Pool Coordinator:</strong> Worker acts as a pool leader, fragments work, and manages pool workers</li>
          <li><strong>Pool Worker:</strong> Worker connects to a pool coordinator and mines assigned fragments</li>
        </ul>
      </div>
    </div>
  `,
  styles: [`
    .workers-container {
      padding: 20px;
      max-width: 1400px;
      margin: 0 auto;
    }
    h1 {
      color: #e0e0e0;
      margin-bottom: 20px;
    }
    .workers-card {
      background-color: #1e1e1e;
      color: #e0e0e0;
      margin-bottom: 20px;
    }
    .switch-card {
      background-color: #1e1e1e;
      color: #e0e0e0;
      margin-bottom: 20px;
    }
    mat-card-title {
      color: #e0e0e0;
    }
    .table-container {
      overflow-x: auto;
    }
    table {
      width: 100%;
    }
    mat-header-cell {
      color: #e0e0e0;
      font-weight: bold;
    }
    mat-cell {
      color: #e0e0e0;
    }
    .mode-badge {
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 0.85em;
      font-weight: bold;
    }
    .mode-standalone {
      background-color: #2196f3;
      color: white;
    }
    .mode-pool-coordinator {
      background-color: #ff9800;
      color: white;
    }
    .mode-pool-worker {
      background-color: #4caf50;
      color: white;
    }
    .policy-badge {
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 0.85em;
      font-weight: bold;
    }
    .policy-accept {
      background-color: #4caf50;
      color: white;
    }
    .policy-reject {
      background-color: #f44336;
      color: white;
    }
    .running-icon {
      color: #4caf50;
    }
    .stopped-icon {
      color: #f44336;
    }
    .running-text {
      color: #4caf50;
      font-weight: bold;
    }
    .stopped-text {
      color: #f44336;
      font-weight: bold;
    }
    .form-field {
      margin: 15px 0;
    }
    mat-form-field {
      width: 100%;
    }
    ::ng-deep .mat-mdc-form-field {
      --mdc-outlined-text-field-outline-color: #e0e0e0;
      --mdc-outlined-text-field-label-text-color: #e0e0e0;
    }
    ::ng-deep .mat-mdc-select-value {
      color: #e0e0e0;
    }
    ::ng-deep .mat-mdc-input-element {
      color: #e0e0e0;
    }
    .actions {
      display: flex;
      gap: 10px;
      margin-top: 20px;
    }
    .info-section {
      background-color: #1e1e1e;
      color: #e0e0e0;
      padding: 20px;
      border-radius: 4px;
    }
    .info-section h3 {
      color: #e0e0e0;
      margin-top: 0;
    }
    .info-section ul {
      color: #e0e0e0;
    }
    .info-section li {
      margin: 8px 0;
    }
  `]
})
export class WorkersComponent implements OnInit {
  private apiService = inject(ApiService);
  workers = signal<WorkerStatus[]>([]);
  displayedColumns: string[] = ['worker_id', 'mode', 'pool_url', 'policy', 'running', 'actions'];
  selectedWorker = signal<WorkerStatus | null>(null);
  targetMode = signal<string>('standalone');
  poolUrl = signal<string>('');
  selectedPoolCoordinator = signal<WorkerStatus | null>(null);
  poolHealth = signal<PoolHealth | null>(null);
  policyDecision = signal<string>('accept');
  policyAction = signal<string>('');
  poolPolicies = signal<Record<string, PoolPolicy>>({});

  ngOnInit() {
    this.loadWorkers();
  }

  loadWorkers() {
    this.apiService.getWorkersStatus().subscribe({
      next: (data) => {
        this.workers.set(data);
        // Load policies for pool coordinators
        data.forEach(worker => {
          if (worker.mode === 'pool-coordinator') {
            this.loadPoolPolicy(worker.worker_id);
          }
        });
      },
      error: (err) => {
        console.error('Failed to load workers:', err);
      }
    });
  }

  loadPoolPolicy(poolId: string) {
    this.apiService.getPoolHealth(poolId).subscribe({
      next: (data) => {
        if (data.voting_policy) {
          this.poolPolicies.update(policies => ({
            ...policies,
            [poolId]: data.voting_policy
          }));
        }
      },
      error: (err) => {
        console.error(`Failed to load policy for ${poolId}:`, err);
      }
    });
  }

  getPolicyDisplay(worker: WorkerStatus): string {
    if (worker.mode !== 'pool-coordinator') {
      return '-';
    }
    const policy = this.poolPolicies()[worker.worker_id];
    if (!policy) {
      return 'Loading...';
    }
    if (policy.decision === 'accept') {
      return 'Accept All';
    }
    if (!policy.action) {
      return 'Reject All';
    }
    // Check if it's both actions
    const actions = policy.action.split(',').map(a => a.trim()).sort();
    if (actions.length === 2 && actions.includes('promulgacion') && actions.includes('derogacion')) {
      return 'Reject All';
    }
    return `Reject: ${policy.action}`;
  }

  openSwitchDialog(worker: WorkerStatus) {
    this.selectedWorker.set(worker);
    this.targetMode.set(worker.mode);
    this.poolUrl.set(worker.pool_url || '');
  }

  cancelSwitch() {
    this.selectedWorker.set(null);
    this.targetMode.set('standalone');
    this.poolUrl.set('');
  }

  canSwitch(): boolean {
    const mode = this.targetMode();
    if (mode === 'pool-worker' && !this.poolUrl()) {
      return false;
    }
    return true;
  }

  confirmSwitch() {
    const worker = this.selectedWorker();
    if (!worker) return;

    const request = {
      target: this.targetMode(),
      pool_url: this.poolUrl()
    };

    this.apiService.switchWorkerMode(worker.worker_id, request).subscribe({
      next: () => {
        this.loadWorkers();
        this.cancelSwitch();
      },
      error: (err) => {
        console.error('Failed to switch worker mode:', err);
        alert('Failed to switch worker mode: ' + err.error?.error || err.message);
      }
    });
  }

  openPolicyDialog(worker: WorkerStatus) {
    if (worker.mode !== 'pool-coordinator') {
      alert('Only pool coordinators can have voting policies');
      return;
    }
    this.selectedPoolCoordinator.set(worker);
    this.loadPoolHealth(worker.worker_id);
  }

  loadPoolHealth(poolId: string) {
    this.apiService.getPoolHealth(poolId).subscribe({
      next: (data) => {
        this.poolHealth.set(data);
        if (data.voting_policy) {
          this.policyDecision.set(data.voting_policy.decision || 'accept');
          this.policyAction.set(data.voting_policy.action || '');
        }
      },
      error: (err) => {
        console.error('Failed to load pool health:', err);
      }
    });
  }

  cancelPolicy() {
    this.selectedPoolCoordinator.set(null);
    this.poolHealth.set(null);
    this.policyDecision.set('accept');
    this.policyAction.set('');
  }

  confirmPolicy() {
    const pool = this.selectedPoolCoordinator();
    if (!pool) return;

    const policy: PoolPolicy = {
      decision: this.policyDecision(),
    };

    if (this.policyDecision() === 'reject' && this.policyAction()) {
      policy.action = this.policyAction();
    }

    this.apiService.setPoolPolicy(pool.worker_id, policy).subscribe({
      next: () => {
        this.loadPoolHealth(pool.worker_id);
        this.loadPoolPolicy(pool.worker_id);
        alert('Pool policy updated successfully');
      },
      error: (err) => {
        console.error('Failed to set pool policy:', err);
        alert('Failed to set pool policy: ' + err.error?.error || err.message);
      }
    });
  }
}
