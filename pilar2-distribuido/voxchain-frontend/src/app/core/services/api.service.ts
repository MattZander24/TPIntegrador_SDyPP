import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Block } from '../models/block.model';
import { Law, LawProposalRequest } from '../models/law.model';
import { Window } from '../models/window.model';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private apiUrl = '/api';

  constructor(private http: HttpClient) {}

  // Chain endpoints
  getChain(): Observable<Block[]> {
    return this.http.get<Block[]>(`${this.apiUrl}/chain`);
  }

  getBlock(blockHash: string): Observable<Block> {
    return this.http.get<Block>(`${this.apiUrl}/chain/${blockHash}`);
  }

  // Laws endpoints
  getLaws(status?: string): Observable<Law[]> {
    const params = status ? { status } : undefined;
    return this.http.get<Law[]>(`${this.apiUrl}/laws`, params ? { params } : {});
  }

  getLaw(lawId: string): Observable<Law> {
    return this.http.get<Law>(`${this.apiUrl}/laws/${lawId}`);
  }

  getLawText(lawId: string): Observable<string> {
    return this.http.get(`${this.apiUrl}/laws/${lawId}/text`, { responseType: 'text' });
  }

  getNextLaw(): Observable<Law | null> {
    return this.http.get<Law | null>(`${this.apiUrl}/laws/next`);
  }

  getLawQueue(): Observable<Law[]> {
    return this.http.get<Law[]>(`${this.apiUrl}/laws/queue`);
  }

  proposeLaw(proposal: LawProposalRequest): Observable<Law> {
    return this.http.post<Law>(`${this.apiUrl}/laws`, proposal);
  }

  // Windows endpoints
  getActiveWindow(): Observable<Window> {
    return this.http.get<Window>(`${this.apiUrl}/windows/active`);
  }

  getWindow(windowId: string): Observable<Window> {
    return this.http.get<Window>(`${this.apiUrl}/windows/${windowId}`);
  }

  // Health endpoint
  getHealth(): Observable<any> {
    return this.http.get(`${this.apiUrl}/health`);
  }
}
