import { api } from "@/lib/api/client";
import type {
  Admin,
  ChangePasswordRequest,
  LoginRequest,
  TokenResponse,
} from "@/lib/types/auth";

export const authApi = {
  login: (payload: LoginRequest) =>
    api.post<TokenResponse>("/auth/login", payload, { auth: false }),
  me: () => api.get<Admin>("/auth/me"),
  changePassword: (payload: ChangePasswordRequest) =>
    api.post<void>("/auth/change-password", payload),
};
