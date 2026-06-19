import { Injectable, signal, effect, DestroyRef } from '@angular/core';
import { Block } from '../models/block.model';
import { Window } from '../models/window.model';

@Injectable({
  providedIn: 'root'
})
export class EventsService {
  latestBlock = signal<Block | null>(null);
  activeWindow = signal<Window | null>(null);
  connectionStatus = signal<'connecting' | 'connected' | 'disconnected'>('disconnected');

  private eventSource: EventSource | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private baseReconnectDelay = 1000; // 1 second

  constructor() {
    this.connect();
  }

  private connect() {
    this.connectionStatus.set('connecting');
    
    try {
      this.eventSource = new EventSource('/api/events');
      
      this.eventSource.onopen = () => {
        this.connectionStatus.set('connected');
        this.reconnectAttempts = 0;
      };

      this.eventSource.onerror = () => {
        this.connectionStatus.set('disconnected');
        this.eventSource?.close();
        this.scheduleReconnect();
      };

      this.eventSource.addEventListener('block_added', (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          this.latestBlock.set(data.block);
        } catch (e) {
          console.error('Failed to parse block_added event:', e);
        }
      });

      this.eventSource.addEventListener('window_opened', (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          this.activeWindow.set(data.window);
        } catch (e) {
          console.error('Failed to parse window_opened event:', e);
        }
      });

      this.eventSource.addEventListener('window_closed', () => {
        this.activeWindow.set(null);
      });

      this.eventSource.addEventListener('law_updated', (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          console.log('Law updated:', data);
        } catch (e) {
          console.error('Failed to parse law_updated event:', e);
        }
      });

    } catch (error) {
      this.connectionStatus.set('disconnected');
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Max reconnection attempts reached');
      return;
    }

    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
      30000 // Max 30 seconds
    );

    this.reconnectAttempts++;
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  disconnect() {
    this.eventSource?.close();
    this.eventSource = null;
    this.connectionStatus.set('disconnected');
  }
}
