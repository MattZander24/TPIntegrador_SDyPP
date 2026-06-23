export interface Law {
  law_id: string;
  author_pubkey: string;
  text_hash: string;
  text_ref?: string;
  text_compressed?: string;
  text_original_len?: number;
  status: string;
  action: string;
  created_at: string;
}

export interface LawProposalRequest {
  law_id?: string;
  author_pubkey: string;
  text: string;
  action: string;
  // Campos firmados por el cliente (A-01). El backend verifica la firma.
  text_hash?: string;
  created_at?: string;
  signature?: string;
}
