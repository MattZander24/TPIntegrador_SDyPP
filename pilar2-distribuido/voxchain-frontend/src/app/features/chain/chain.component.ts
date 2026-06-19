import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { ApiService } from '../../core/services/api.service';
import { Block } from '../../core/models/block.model';

@Component({
  selector: 'app-chain',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatTableModule, MatButtonModule],
  template: `
    <div class="chain-container">
      <h1>Blockchain</h1>
      
      <mat-card>
        <mat-card-content>
          <table mat-table [dataSource]="blocks()">
            <ng-container matColumnDef="block_hash">
              <th mat-header-cell *matHeaderCellDef>Block Hash</th>
              <td mat-cell *matCellDef="let block">
                <code>{{ block.block_hash.slice(0, 12) }}...</code>
              </td>
            </ng-container>

            <ng-container matColumnDef="law_id">
              <th mat-header-cell *matHeaderCellDef>Law ID</th>
              <td mat-cell *matCellDef="let block">{{ block.law_id }}</td>
            </ng-container>

            <ng-container matColumnDef="action">
              <th mat-header-cell *matHeaderCellDef>Action</th>
              <td mat-cell *matCellDef="let block">{{ block.action }}</td>
            </ng-container>

            <ng-container matColumnDef="nonce">
              <th mat-header-cell *matHeaderCellDef>Nonce</th>
              <td mat-cell *matCellDef="let block">{{ block.nonce }}</td>
            </ng-container>

            <ng-container matColumnDef="winning_node">
              <th mat-header-cell *matHeaderCellDef>Winner</th>
              <td mat-cell *matCellDef="let block">{{ block.winning_node_or_pool }}</td>
            </ng-container>

            <ng-container matColumnDef="timestamp">
              <th mat-header-cell *matHeaderCellDef>Timestamp</th>
              <td mat-cell *matCellDef="let block">{{ block.timestamp }}</td>
            </ng-container>

            <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
            <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
          </table>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .chain-container {
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
    code {
      font-family: 'Courier New', monospace;
      background-color: #2a2a2a;
      padding: 2px 6px;
      border-radius: 3px;
    }
  `]
})
export class ChainComponent implements OnInit {
  private apiService = inject(ApiService);
  blocks = signal<Block[]>([]);
  displayedColumns: string[] = ['block_hash', 'law_id', 'action', 'nonce', 'winning_node', 'timestamp'];

  ngOnInit() {
    this.loadChain();
  }

  private loadChain() {
    this.apiService.getChain().subscribe((blocks: Block[]) => {
      this.blocks.set(blocks.reverse());
    });
  }
}
