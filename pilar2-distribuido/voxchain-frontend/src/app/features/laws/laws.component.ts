import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatTabsModule } from '@angular/material/tabs';
import { ApiService } from '../../core/services/api.service';
import { Law } from '../../core/models/law.model';

@Component({
  selector: 'app-laws',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatTableModule, MatButtonModule, MatTabsModule],
  template: `
    <div class="laws-container">
      <h1>Laws</h1>
      
      <mat-card>
        <mat-card-content>
          <mat-tab-group>
            <mat-tab label="All">
              <ng-template matTabContent>
                <table mat-table [dataSource]="allLaws()">
                  <ng-container matColumnDef="law_id">
                    <th mat-header-cell *matHeaderCellDef>Law ID</th>
                    <td mat-cell *matCellDef="let law">{{ law.law_id }}</td>
                  </ng-container>

                  <ng-container matColumnDef="author">
                    <th mat-header-cell *matHeaderCellDef>Author</th>
                    <td mat-cell *matCellDef="let law">{{ law.author_pubkey.slice(0, 12) }}...</td>
                  </ng-container>

                  <ng-container matColumnDef="status">
                    <th mat-header-cell *matHeaderCellDef>Status</th>
                    <td mat-cell *matCellDef="let law">{{ law.status }}</td>
                  </ng-container>

                  <ng-container matColumnDef="action">
                    <th mat-header-cell *matHeaderCellDef>Action</th>
                    <td mat-cell *matCellDef="let law">{{ law.action }}</td>
                  </ng-container>

                  <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
                  <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
                </table>
              </ng-template>
            </mat-tab>
            <mat-tab label="Pending">
              <ng-template matTabContent>
                <table mat-table [dataSource]="pendingLaws()">
                  <ng-container matColumnDef="law_id">
                    <th mat-header-cell *matHeaderCellDef>Law ID</th>
                    <td mat-cell *matCellDef="let law">{{ law.law_id }}</td>
                  </ng-container>

                  <ng-container matColumnDef="author">
                    <th mat-header-cell *matHeaderCellDef>Author</th>
                    <td mat-cell *matCellDef="let law">{{ law.author_pubkey.slice(0, 12) }}...</td>
                  </ng-container>

                  <ng-container matColumnDef="status">
                    <th mat-header-cell *matHeaderCellDef>Status</th>
                    <td mat-cell *matCellDef="let law">{{ law.status }}</td>
                  </ng-container>

                  <ng-container matColumnDef="action">
                    <th mat-header-cell *matHeaderCellDef>Action</th>
                    <td mat-cell *matCellDef="let law">{{ law.action }}</td>
                  </ng-container>

                  <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
                  <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
                </table>
              </ng-template>
            </mat-tab>
            <mat-tab label="Promulgated">
              <ng-template matTabContent>
                <table mat-table [dataSource]="promulgatedLaws()">
                  <ng-container matColumnDef="law_id">
                    <th mat-header-cell *matHeaderCellDef>Law ID</th>
                    <td mat-cell *matCellDef="let law">{{ law.law_id }}</td>
                  </ng-container>

                  <ng-container matColumnDef="author">
                    <th mat-header-cell *matHeaderCellDef>Author</th>
                    <td mat-cell *matCellDef="let law">{{ law.author_pubkey.slice(0, 12) }}...</td>
                  </ng-container>

                  <ng-container matColumnDef="status">
                    <th mat-header-cell *matHeaderCellDef>Status</th>
                    <td mat-cell *matCellDef="let law">{{ law.status }}</td>
                  </ng-container>

                  <ng-container matColumnDef="action">
                    <th mat-header-cell *matHeaderCellDef>Action</th>
                    <td mat-cell *matCellDef="let law">{{ law.action }}</td>
                  </ng-container>

                  <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
                  <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
                </table>
              </ng-template>
            </mat-tab>
          </mat-tab-group>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .laws-container {
      padding: 20px;
      max-width: 1400px;
      margin: 0 auto;
    }
    h1 {
      color: #e0e0e0;
    }
    mat-card {
      background-color: #1e1e1e;
      color: #e0e0e0;
    }
    table {
      width: 100%;
    }
    th {
      color: #64b5f6;
    }
    td {
      color: #b0b0b0;
    }
  `]
})
export class LawsComponent implements OnInit {
  private apiService = inject(ApiService);
  allLaws = signal<Law[]>([]);
  pendingLaws = signal<Law[]>([]);
  promulgatedLaws = signal<Law[]>([]);
  displayedColumns: string[] = ['law_id', 'author', 'status', 'action'];

  ngOnInit() {
    this.loadLaws();
  }

  private loadLaws() {
    this.apiService.getLaws().subscribe((laws: Law[]) => {
      this.allLaws.set(laws);
      this.pendingLaws.set(laws.filter((l: Law) => l.status === 'pending_queue'));
      this.promulgatedLaws.set(laws.filter((l: Law) => l.status === 'promulgated'));
    });
  }
}
