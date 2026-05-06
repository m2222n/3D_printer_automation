/**
 * 사용자 로그인 인증 서비스
 * - JWT 토큰 localStorage 저장
 * - fetch wrapper에서 자동 첨부
 * - 응답의 X-New-Token (sliding refresh) 자동 교체
 * - 401 응답 시 로그아웃 + 로그인 페이지 이동
 */

const TOKEN_KEY = "orinu_auth_token";
const USERNAME_KEY = "orinu_auth_username";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in_days: number;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUsername(): string | null {
  return localStorage.getItem(USERNAME_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function setUsername(username: string): void {
  localStorage.setItem(USERNAME_KEY, username);
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}

/**
 * 로그인 — 토큰 저장.
 * 실패 시 throw.
 */
export async function login(username: string, password: string): Promise<void> {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("아이디 또는 비밀번호가 올바르지 않습니다.");
    }
    if (response.status === 503) {
      throw new Error("서버 인증 설정이 누락되었습니다. 관리자에게 문의하세요.");
    }
    throw new Error(`로그인 실패 (${response.status})`);
  }

  const data: LoginResponse = await response.json();
  setToken(data.access_token);
  setUsername(username);
}

/**
 * 로그아웃 — 토큰 삭제 + (옵션) 서버 알림.
 * 페이지 이동은 호출 측에서 처리.
 */
export async function logout(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      headers: authHeaders(),
    });
  } catch {
    // 서버 응답 실패해도 클라이언트 측 정리는 진행
  }
  clearAuth();
}

/**
 * 토큰 유효성 확인 — 페이지 진입 시 호출.
 * 만료/무효 토큰이면 false 반환 → 로그인 화면으로 보내야 함.
 */
export async function verifyToken(): Promise<boolean> {
  const token = getToken();
  if (!token) return false;

  try {
    const response = await fetch("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * 현재 토큰을 Bearer 헤더 형태로 반환. 토큰 없으면 빈 객체.
 */
export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * 인증된 fetch — 모든 API 호출이 이걸 거치도록.
 * - 토큰 자동 첨부
 * - 응답의 X-New-Token 자동 교체 (sliding refresh)
 * - 401 시 인증 정보 클리어 + window 이벤트 디스패치 (App에서 로그인 화면 전환)
 */
export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(input, { ...init, headers });

  // Sliding refresh — 새 토큰 받으면 교체
  const newToken = response.headers.get("X-New-Token");
  if (newToken) {
    setToken(newToken);
  }

  // 401 → 즉시 로그아웃
  if (response.status === 401) {
    clearAuth();
    window.dispatchEvent(new Event("auth:expired"));
  }

  return response;
}
