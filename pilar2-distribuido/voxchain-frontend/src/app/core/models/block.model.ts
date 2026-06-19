export interface Block {
  previous_hash: string;
  law_id: string;
  action: string;
  n_zeros_required: number;
  nonce: number;
  winning_node_or_pool: string;
  voting_window_id: string;
  block_hash: string;
  timestamp: string;
}
