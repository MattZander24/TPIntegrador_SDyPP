import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { RouterModule } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { IdentityService } from '../../core/services/identity.service';
import { Law } from '../../core/models/law.model';

@Component({
  selector: 'app-propose-law',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterModule,
    MatCardModule, MatButtonModule, MatInputModule,
    MatSelectModule, MatFormFieldModule, MatIconModule,
  ],
  template: `
    <div class="propose-container">
      <h1>Propose Law</h1>

      <div *ngIf="!identityService.identity()" class="no-identity">
        <mat-card>
          <mat-card-content>
            <p>You need to <a routerLink="/identity">register an identity</a> before proposing a law.</p>
          </mat-card-content>
        </mat-card>
      </div>

      <mat-card *ngIf="identityService.identity()">
        <mat-card-content>
          <div class="form">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Action</mat-label>
              <mat-select [(ngModel)]="action">
                <mat-option value="promulgacion">Promulgar</mat-option>
                <mat-option value="derogacion">Derogar</mat-option>
              </mat-select>
            </mat-form-field>

            <div *ngIf="action === 'derogacion'">
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Law ID to Repeal</mat-label>
                <mat-select [(ngModel)]="lawIdToRepeal" placeholder="Select a promulgated law">
                  <mat-option *ngFor="let law of promulgatedLaws()" [value]="law.law_id">
                    {{ law.law_id }}
                  </mat-option>
                </mat-select>
                <mat-hint>Select the promulgated law you want to repeal</mat-hint>
              </mat-form-field>
              <p *ngIf="promulgatedLaws().length === 0" class="hint">No hay leyes promulgadas para derogar.</p>
            </div>

            <div *ngIf="action !== 'derogacion'">
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Law Text</mat-label>
                <textarea matInput [(ngModel)]="text" rows="10" placeholder="Enter the law text here..."></textarea>
              </mat-form-field>

              <div class="file-upload">
                <p class="hint">Or upload a text file:</p>
                <input type="file" accept=".txt" (change)="onFileSelected($event)" />
              </div>
            </div>

            <div *ngIf="error()" class="error-msg">{{ error() }}</div>
            <div *ngIf="success()" class="success-msg">
              {{ action === 'derogacion' ? 'Repeal proposed successfully! Law ID:' : 'Law proposed successfully! ID:' }} {{ success() }}
            </div>

            <div class="actions">
              <button mat-raised-button color="primary" (click)="submit()" [disabled]="submitting() || !canSubmit()">
                {{ submitting() ? 'Submitting...' : (action === 'derogacion' ? 'Propose Repeal' : 'Propose Law') }}
              </button>
            </div>
          </div>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .propose-container {
      padding: 20px;
      max-width: 800px;
      margin: 0 auto;
    }
    h1 { color: #e0e0e0; }
    mat-card {
      background-color: #1e1e1e;
      color: #e0e0e0;
    }
    .full-width { width: 100%; margin-bottom: 16px; }
    .hint { color: #888; font-size: 0.9rem; }
    .file-upload {
      margin-bottom: 16px;
      color: #b0b0b0;
    }
    .actions { margin-top: 16px; }
    .error-msg {
      color: #f44336;
      padding: 8px;
      margin: 8px 0;
      background-color: #2d1b1b;
      border-radius: 4px;
    }
    .success-msg {
      color: #4caf50;
      padding: 8px;
      margin: 8px 0;
      background-color: #1b2d1b;
      border-radius: 4px;
    }
    .no-identity p {
      color: #888;
    }
    .no-identity a { color: #64b5f6; }
  `]
})
export class ProposeLawComponent {
  private apiService = inject(ApiService);
  identityService = inject(IdentityService);

  text = signal('');
  action = 'promulgacion';
  lawIdToRepeal = '';
  submitting = signal(false);
  error = signal('');
  success = signal('');
  promulgatedLaws = signal<Law[]>([]);

  constructor() {
    this.apiService.getLaws('promulgated').subscribe((laws: Law[]) => {
      this.promulgatedLaws.set(laws);
    });
  }

  canSubmit(): boolean {
    if (this.submitting()) return false;
    if (this.action === 'derogacion') return !!this.lawIdToRepeal;
    return !!this.text();
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      this.text.set(reader.result as string);
    };
    reader.readAsText(file);
  }

  async submit() {
    const id = this.identityService.identity();
    if (!id || !this.canSubmit()) return;

    this.submitting.set(true);
    this.error.set('');
    this.success.set('');

    try {
      const text = this.action === 'derogacion' ? '' : this.text();
      const law_id = this.action === 'derogacion'
        ? this.lawIdToRepeal
        : `ley-${crypto.randomUUID().slice(0, 8)}`;
      const text_hash = await this.identityService.sha256Hex(text);
      const created_at = new Date().toISOString();

      // En modo demo la clave privada está en el worker (backend); se envía sin firma.
      // REQUIRE_SIGNATURES=false en el backend acepta signature vacío.
      let signature = '';
      if (!this.identityService.isDemoMode()) {
        const message = `${id.pubkey}|${this.action}|${text_hash}|${law_id}|${created_at}`;
        signature = await this.identityService.sign(message);
      }

      const payload: any = {
        author_pubkey: id.pubkey,
        action: this.action,
        law_id,
        text,
        text_hash,
        created_at,
        signature,
      };

      const result = await firstValueFrom(this.apiService.proposeLaw(payload));
      this.success.set(result?.law_id ?? 'unknown');
      if (this.action !== 'derogacion') {
        this.text.set('');
      } else {
        this.lawIdToRepeal = '';
      }
    } catch (e: any) {
      this.error.set(e?.error?.detail || e.message || 'Failed to propose');
    } finally {
      this.submitting.set(false);
    }
  }
}
