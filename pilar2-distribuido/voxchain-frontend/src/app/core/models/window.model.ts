export interface Window {
  voting_window_id: string;
  law_id: string;
  action: string;
  n_zeros_required: number;
  opened_at: string;
  deadline: string;
  partial_hash_base: string;
  result?: string;
  winning_nonce?: number;
  winning_node_or_pool?: string;
}
