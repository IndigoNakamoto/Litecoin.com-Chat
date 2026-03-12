/**
 * API client for admin frontend.
 * Handles authentication and settings API calls.
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const AUTH_TOKEN_KEY = "admin_token";

/**
 * Get the stored admin token from localStorage.
 */
function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

/**
 * Store the admin token in localStorage.
 */
function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

/**
 * Remove the admin token from localStorage.
 */
function removeToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

/**
 * Create authorization header with stored token.
 */
function getAuthHeader(): Record<string, string> {
  const token = getToken();
  if (!token) {
    return {};
  }
  return {
    Authorization: `Bearer ${token}`,
  };
}

/**
 * Make an authenticated API request.
 */
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BACKEND_URL}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...getAuthHeader(),
    ...(options.headers || {}),
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      error: "Unknown error",
      message: `Request failed with status ${response.status}`,
    }));
    throw new Error(error.message || error.error || "Request failed");
  }

  return response.json();
}

/**
 * Authentication API client.
 */
export const authApi = {
  /**
   * Login with admin token.
   */
  async login(token: string): Promise<{ authenticated: boolean; message: string }> {
    // Verify token with backend first
    const url = `${BACKEND_URL}/api/v1/admin/auth/login`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        error: "Unknown error",
        message: `Login failed with status ${response.status}`,
      }));
      throw new Error(error.message || error.error || "Login failed");
    }

    const result = await response.json();

    // Store token only after successful authentication
    setToken(token);

    return result;
  },

  /**
   * Verify current token is still valid.
   */
  async verify(): Promise<{ authenticated: boolean; message: string }> {
    const token = getToken();
    if (!token) {
      throw new Error("No token found");
    }

    return apiRequest<{ authenticated: boolean; message: string }>(
      "/api/v1/admin/auth/verify",
      {
        method: "GET",
      }
    );
  },

  /**
   * Logout and clear stored token.
   */
  logout(): void {
    removeToken();
  },
};

/**
 * Settings API client.
 */
export const settingsApi = {
  /**
   * Get abuse prevention settings.
   */
  async getSettings(): Promise<{
    settings: Record<string, any>;
    sources: Record<string, "redis" | "environment">;
  }> {
    return apiRequest<{
      settings: Record<string, any>;
      sources: Record<string, "redis" | "environment">;
    }>("/api/v1/admin/settings/abuse-prevention", {
      method: "GET",
    });
  },

  /**
   * Update abuse prevention settings.
   */
  async updateSettings(
    settings: Record<string, any>
  ): Promise<{ message: string }> {
    return apiRequest<{ message: string }>(
      "/api/v1/admin/settings/abuse-prevention",
      {
        method: "PUT",
        body: JSON.stringify(settings),
      }
    );
  },
};

/**
 * Redis API client.
 */
export const redisApi = {
  /**
   * Get Redis statistics (bans and throttles).
   */
  async getStats(): Promise<{
    bans: { total: number; patterns: string[] };
    throttles: { total: number; patterns: string[] };
  }> {
    return apiRequest<{
      bans: { total: number; patterns: string[] };
      throttles: { total: number; patterns: string[] };
    }>("/api/v1/admin/redis/stats", {
      method: "GET",
    });
  },

  /**
   * Clear all bans from Redis.
   */
  async clearBans(): Promise<{
    success: boolean;
    deleted_count: number;
    message: string;
  }> {
    return apiRequest<{
      success: boolean;
      deleted_count: number;
      message: string;
    }>("/api/v1/admin/redis/clear-bans", {
      method: "POST",
    });
  },

  /**
   * Clear all throttles from Redis.
   */
  async clearThrottles(): Promise<{
    success: boolean;
    deleted_count: number;
    message: string;
  }> {
    return apiRequest<{
      success: boolean;
      deleted_count: number;
      message: string;
    }>("/api/v1/admin/redis/clear-throttles", {
      method: "POST",
    });
  },
};

/**
 * Cache API client.
 */
export const cacheApi = {
  /**
   * Get cache statistics.
   */
  async getStats(): Promise<{
    cache_size: number;
    cache_type: string;
  }> {
    return apiRequest<{
      cache_size: number;
      cache_type: string;
    }>("/api/v1/admin/cache/suggested-questions/stats", {
      method: "GET",
    });
  },

  /**
   * Clear the suggested questions cache.
   */
  async clear(): Promise<{
    success: boolean;
    cleared_count: number;
    message: string;
  }> {
    return apiRequest<{
      success: boolean;
      cleared_count: number;
      message: string;
    }>("/api/v1/admin/cache/suggested-questions/clear", {
      method: "POST",
    });
  },

  /**
   * Refresh the suggested questions cache.
   */
  async refresh(): Promise<{
    success: boolean;
    message: string;
    status: string;
  }> {
    return apiRequest<{
      success: boolean;
      message: string;
      status: string;
    }>("/api/v1/admin/cache/suggested-questions/refresh", {
      method: "POST",
    });
  },
};

/**
 * Users API client.
 */
export const usersApi = {
  /**
   * Get user statistics.
   */
  async getStats(days: number = 30): Promise<{
    total_unique_users: number;
    today_unique_users: number;
    average_users_per_day: number;
    users_over_time: Array<{ date: string; unique_users: number }>;
    days_tracked: number;
  }> {
    return apiRequest<{
      total_unique_users: number;
      today_unique_users: number;
      average_users_per_day: number;
      users_over_time: Array<{ date: string; unique_users: number }>;
      days_tracked: number;
    }>(`/api/v1/admin/users/stats?days=${days}`, {
      method: "GET",
    });
  },
};

/**
 * Knowledge Candidates API client.
 */
export const knowledgeCandidatesApi = {
  async list(params: {
    status?: string;
    limit?: number;
    offset?: number;
    sort_by?: string;
    sort_order?: number;
  } = {}): Promise<{
    candidates: KnowledgeCandidate[];
    total: number;
    limit: number;
    offset: number;
  }> {
    const searchParams = new URLSearchParams();
    if (params.status) searchParams.set("status", params.status);
    if (params.limit) searchParams.set("limit", String(params.limit));
    if (params.offset) searchParams.set("offset", String(params.offset));
    if (params.sort_by) searchParams.set("sort_by", params.sort_by);
    if (params.sort_order !== undefined) searchParams.set("sort_order", String(params.sort_order));
    const qs = searchParams.toString();
    return apiRequest(`/api/v1/admin/knowledge-candidates${qs ? `?${qs}` : ""}`);
  },

  async get(id: string): Promise<{ candidate: KnowledgeCandidate }> {
    return apiRequest(`/api/v1/admin/knowledge-candidates/${id}`);
  },

  async update(
    id: string,
    data: { status?: "approved" | "rejected"; admin_notes?: string }
  ): Promise<{ candidate: KnowledgeCandidate; updated: boolean }> {
    return apiRequest(`/api/v1/admin/knowledge-candidates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async publish(id: string): Promise<{
    published: boolean;
    payload_article_id: string;
    candidate_id: string;
  }> {
    return apiRequest(`/api/v1/admin/knowledge-candidates/${id}/publish`, {
      method: "POST",
    });
  },

  async stats(): Promise<{
    by_status: Record<string, { count: number; total_frequency: number }>;
    top_pending_topics: Array<{ topic: string; count: number; total_frequency: number }>;
    total_candidates: number;
  }> {
    return apiRequest("/api/v1/admin/knowledge-candidates/stats");
  },
};

export interface KnowledgeCandidate {
  id: string;
  user_question: string;
  request_id: string;
  timestamp: string;
  generated_answer: string;
  grounding_sources: Array<{ url?: string; title?: string }>;
  kb_sources_used: Array<Record<string, unknown>>;
  kb_coverage_score: number;
  topic_cluster: string | null;
  question_frequency: number;
  status: "pending" | "approved" | "rejected" | "published";
  reviewed_by: string | null;
  reviewed_at: string | null;
  admin_notes: string | null;
  payload_article_id: string | null;
  similar_candidate_ids: string[];
}

/**
 * Question logs API client.
 */
export const questionLogsApi = {
  /**
   * Get recent question logs.
   */
  async getRecentLogs(limit: number = 100): Promise<{
    logs: Array<{
      id: string;
      request_id: string;
      timestamp: string;
      user_question: string;
      assistant_response_length: number;
      input_tokens: number;
      output_tokens: number;
      cost_usd: number;
      model: string;
      duration_seconds: number;
      status: string;
      sources_count: number;
      cache_hit: boolean;
      cache_type: string | null;
      endpoint_type: string;
    }>;
    count: number;
  }> {
    return apiRequest<{
      logs: Array<{
        id: string;
        request_id: string;
        timestamp: string;
        user_question: string;
        assistant_response_length: number;
        input_tokens: number;
        output_tokens: number;
        cost_usd: number;
        model: string;
        duration_seconds: number;
        status: string;
        sources_count: number;
        cache_hit: boolean;
        cache_type: string | null;
        endpoint_type: string;
      }>;
      count: number;
    }>(`/api/v1/admin/llm-logs/recent?limit=${limit}`, {
      method: "GET",
    });
  },
};

