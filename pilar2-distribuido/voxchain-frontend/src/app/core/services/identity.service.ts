import { Injectable, signal, computed, inject } from '@angular/core';
import { AccountsService } from './accounts.service';

export interface Identity {
  pubkey: string;
  exportedPrivkey: string | null; // null in demo mode
  username?: string; // demo account username
  isDemo?: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class IdentityService {
  identity = signal<Identity | null>(null);
  isDemoMode = computed(() => {
    const id = this.identity();
    return id?.isDemo === true;
  });

  private storageKey = 'voxchain_identity';
  private accountsService = inject(AccountsService);

  constructor() {
    this.loadFromStorage();
    this.syncWithDemoAccount();
  }

  private loadFromStorage() {
    const raw = localStorage.getItem(this.storageKey);
    if (raw) {
      try {
        this.identity.set(JSON.parse(raw));
      } catch {
        localStorage.removeItem(this.storageKey);
      }
    }
  }

  private syncWithDemoAccount() {
    // If a demo account is selected, use its pubkey
    const demoAccount = this.accountsService.selectedAccount();
    if (demoAccount) {
      this.identity.set({
        pubkey: demoAccount.pubkey,
        exportedPrivkey: null,
        username: demoAccount.username,
        isDemo: true
      });
    }
  }

  async generateKeypair(): Promise<Identity> {
    const keypair = await crypto.subtle.generateKey(
      { name: 'ECDSA', namedCurve: 'P-256' },
      true,
      ['sign', 'verify']
    );

    const pubkeyRaw = await crypto.subtle.exportKey('spki', keypair.publicKey);
    const privkeyRaw = await crypto.subtle.exportKey('pkcs8', keypair.privateKey);

    const pubkey = this.arrayBufferToBase64(pubkeyRaw);
    const exportedPrivkey = this.arrayBufferToBase64(privkeyRaw);

    const identity: Identity = { pubkey, exportedPrivkey, isDemo: false };
    localStorage.setItem(this.storageKey, JSON.stringify(identity));
    this.identity.set(identity);
    return identity;
  }

  /**
   * Firma un mensaje con la clave privada local (ECDSA P-256 / SHA-256).
   * En modo demo, no firma (la clave privada está en el backend).
   * La privada nunca sale del navegador (AGENT.md 3.1): se importa, firma y descarta.
   * Devuelve la firma cruda (P1363, r||s) en base64, el formato que verifica el backend.
   */
  async sign(message: string): Promise<string> {
    const id = this.identity();
    if (!id) throw new Error('no identity');
    
    // In demo mode, signing is handled by the backend
    if (id.isDemo) {
      throw new Error('Demo mode: signing is handled by backend');
    }
    
    if (!id.exportedPrivkey) {
      throw new Error('No private key available');
    }
    
    const key = await crypto.subtle.importKey(
      'pkcs8',
      this.base64ToArrayBuffer(id.exportedPrivkey),
      { name: 'ECDSA', namedCurve: 'P-256' },
      false,
      ['sign']
    );
    const sig = await crypto.subtle.sign(
      { name: 'ECDSA', hash: 'SHA-256' },
      key,
      new TextEncoder().encode(message)
    );
    return this.arrayBufferToBase64(sig);
  }

  /** SHA-256 del texto en hex (debe coincidir con hashlib.sha256 del backend). */
  async sha256Hex(text: string): Promise<string> {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  }

  clearIdentity() {
    localStorage.removeItem(this.storageKey);
    this.identity.set(null);
  }

  private base64ToArrayBuffer(b64: string): ArrayBuffer {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }

  getPubkeyShort(): string {
    const id = this.identity();
    if (!id) return '';
    return id.pubkey.slice(0, 16) + '...';
  }

  getUsername(): string | undefined {
    const id = this.identity();
    return id?.username;
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
}
