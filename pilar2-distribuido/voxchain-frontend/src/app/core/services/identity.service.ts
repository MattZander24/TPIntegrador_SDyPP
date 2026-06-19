import { Injectable, signal } from '@angular/core';

export interface Identity {
  pubkey: string;
  exportedPrivkey: string;
}

@Injectable({
  providedIn: 'root'
})
export class IdentityService {
  identity = signal<Identity | null>(null);

  private storageKey = 'voxchain_identity';

  constructor() {
    this.loadFromStorage();
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

    const identity: Identity = { pubkey, exportedPrivkey };
    localStorage.setItem(this.storageKey, JSON.stringify(identity));
    this.identity.set(identity);
    return identity;
  }

  clearIdentity() {
    localStorage.removeItem(this.storageKey);
    this.identity.set(null);
  }

  getPubkeyShort(): string {
    const id = this.identity();
    if (!id) return '';
    return id.pubkey.slice(0, 16) + '...';
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
