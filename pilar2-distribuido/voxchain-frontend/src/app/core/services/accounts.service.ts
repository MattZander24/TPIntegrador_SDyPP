import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface DemoAccount {
  username: string;
  worker_id: string;
  mode: string;
  pubkey: string;
  status: 'available' | 'occupied';
  occupied_by?: string;
  occupied_at?: string;
}

export interface ReserveResponse {
  status: 'reserved' | 'already_reserved';
  username: string;
  worker_id: string;
  mode: string;
  pubkey: string;
}

export interface ReleaseResponse {
  status: 'released' | 'not_occupied';
  username: string;
}

@Injectable({
  providedIn: 'root'
})
export class AccountsService {
  private apiUrl = '/api/accounts';
  sessionId = signal<string | null>(null);
  selectedAccount = signal<DemoAccount | null>(null);

  constructor(private http: HttpClient) {
    this.loadSession();
  }

  private loadSession() {
    const savedSession = localStorage.getItem('voxchain_session_id');
    const savedAccount = localStorage.getItem('voxchain_selected_account');
    
    if (savedSession) {
      this.sessionId.set(savedSession);
    }
    if (savedAccount) {
      try {
        this.selectedAccount.set(JSON.parse(savedAccount));
      } catch {
        localStorage.removeItem('voxchain_selected_account');
      }
    }
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  ensureSession(): string {
    let sid = this.sessionId();
    if (!sid) {
      sid = this.generateSessionId();
      this.sessionId.set(sid);
      localStorage.setItem('voxchain_session_id', sid);
    }
    return sid;
  }

  listAccounts(): Observable<DemoAccount[]> {
    return this.http.get<DemoAccount[]>(this.apiUrl);
  }

  reserveAccount(username: string): Observable<ReserveResponse> {
    const sessionId = this.ensureSession();
    return this.http.post<ReserveResponse>(`${this.apiUrl}/reserve`, {
      username,
      session_id: sessionId
    });
  }

  releaseAccount(username: string): Observable<ReleaseResponse> {
    const sessionId = this.sessionId();
    if (!sessionId) {
      throw new Error('No active session');
    }
    return this.http.post<ReleaseResponse>(`${this.apiUrl}/release`, {
      username,
      session_id: sessionId
    });
  }

  setSelectedAccount(account: DemoAccount | null) {
    this.selectedAccount.set(account);
    if (account) {
      localStorage.setItem('voxchain_selected_account', JSON.stringify(account));
    } else {
      localStorage.removeItem('voxchain_selected_account');
    }
  }

  clearSession() {
    this.sessionId.set(null);
    this.selectedAccount.set(null);
    localStorage.removeItem('voxchain_session_id');
    localStorage.removeItem('voxchain_selected_account');
  }

  getPubkey(): string | null {
    const account = this.selectedAccount();
    return account ? account.pubkey : null;
  }
}
