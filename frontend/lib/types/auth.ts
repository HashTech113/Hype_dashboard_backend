export type Role = "SUPER_ADMIN" | "ADMIN" | "VIEWER";

export interface Admin {
  id: number;
  username: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}
