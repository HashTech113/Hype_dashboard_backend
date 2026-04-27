import Cookies from "js-cookie";

const TOKEN_COOKIE = "aa_token";
const TOKEN_EXPIRES_DAYS = 1;

export function getToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return Cookies.get(TOKEN_COOKIE);
}

export function setToken(token: string, expiresDays: number = TOKEN_EXPIRES_DAYS): void {
  Cookies.set(TOKEN_COOKIE, token, {
    expires: expiresDays,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
  });
}

export function clearToken(): void {
  Cookies.remove(TOKEN_COOKIE);
}

export const TOKEN_COOKIE_NAME = TOKEN_COOKIE;
