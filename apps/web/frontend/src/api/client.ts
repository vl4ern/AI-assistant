const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export async function apiRequest<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `API error: ${response.status}`;

    try {
      const data = await response.json();

      if (typeof data?.detail === 'string') {
        detail = data.detail;
      }
    } catch {
      // Ответ без JSON.
    }

    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
