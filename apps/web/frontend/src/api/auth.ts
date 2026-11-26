import { apiRequest } from './client';

export type AuthUser = {
  id: string;
  username: string;
};

export type AuthResponse = {
  token: string;
  user: AuthUser;
};

export function login(username: string, password: string): Promise<AuthResponse> {
  return apiRequest<AuthResponse>('/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function register(username: string, password: string): Promise<AuthResponse> {
  return apiRequest<AuthResponse>('/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function getCurrentUser(): Promise<AuthUser> {
  return apiRequest<AuthUser>('/v1/auth/me');
}
