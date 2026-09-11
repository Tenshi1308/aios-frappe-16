export interface ChatSession {
  name: string | number;
  chat_id: string;
  first_name: string;
  last_name?: string;
  username?: string;
  status: string;
  last_interaction: string;
  lead?: string | null;
  last_message?: string;
  sales_order?: string | null;
  order_total?: number;
}

export interface OrderInfo {
  sales_order: string;
  grand_total: number;
  items_summary: string;
}

export interface ChatMessage {
  name: string | number;
  session: string | number;
  sender: "user" | "bot";
  message: string;
  sent_at: string;
  sales_order?: string | null;
  order_info?: OrderInfo;
}

export interface ChatbotSettings {
  persona_tone: string;
  custom_instructions: string;
  bot_username?: string;
  is_active?: boolean;
}

