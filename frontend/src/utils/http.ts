import axios from 'axios';
import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { ElMessage } from 'element-plus';

const stripTrailingSlash = (value: string) => value.replace(/\/+$/, '');
const CONFIGURED_LEARNER_USER_ID = String(import.meta.env.VITE_LEARNER_USER_ID || '').trim();
export const LEARNER_ID_STORAGE_KEY = 'lingzhi_learner_id_v1';
let inMemoryLearnerId = '';

const createLearnerId = () => {
  const randomId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
  return `learner_${randomId}`;
};

export const getLearnerIdentity = (): string => {
  if (CONFIGURED_LEARNER_USER_ID && CONFIGURED_LEARNER_USER_ID !== 'default_user') {
    return CONFIGURED_LEARNER_USER_ID;
  }
  if (inMemoryLearnerId) return inMemoryLearnerId;
  try {
    const saved = localStorage.getItem(LEARNER_ID_STORAGE_KEY)?.trim() || '';
    if (saved && saved !== 'default_user') {
      inMemoryLearnerId = saved;
      return saved;
    }
    inMemoryLearnerId = createLearnerId();
    localStorage.setItem(LEARNER_ID_STORAGE_KEY, inMemoryLearnerId);
    return inMemoryLearnerId;
  } catch {
    inMemoryLearnerId = createLearnerId();
    return inMemoryLearnerId;
  }
};

export const API_BASE = stripTrailingSlash(
  import.meta.env.VITE_API_BASE_URL || import.meta.env.BASE_URL || ''
);
export const withApiBase = (path: string) => `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;

// ============================================================================
// HTTP Client Configuration
// ============================================================================

const http: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 180000, // 180 seconds for LLM operations
});

export const applyLearnerIdentity = (
  config: InternalAxiosRequestConfig,
  userId = getLearnerIdentity(),
): InternalAxiosRequestConfig => {
  const normalized = userId.trim();
  if (!normalized) return config;
  config.headers.set('X-User-Id', normalized);
  return config;
};

export const learnerIdentityHeaders = (
  initial: HeadersInit = {},
  userId = getLearnerIdentity(),
): Headers => {
  const headers = new Headers(initial);
  const normalized = userId.trim();
  if (normalized) headers.set('X-User-Id', normalized);
  return headers;
};

// ============================================================================
// Error Handling Utilities
// ============================================================================

interface ErrorResponse {
  detail?: string;
  message?: string;
  error?: string;
}

interface ErrorConfig {
  showMessage: boolean;
  customHandler?: (error: AxiosError) => void;
}

declare module 'axios' {
  export interface AxiosRequestConfig {
    silentError?: boolean;
  }

  export interface InternalAxiosRequestConfig {
    silentError?: boolean;
  }
}

const DEFAULT_ERROR_CONFIG: ErrorConfig = {
  showMessage: true,
};

const handledErrors = new WeakSet<object>();
const NETWORK_ERROR_MESSAGE_COOLDOWN_MS = 10000;
let lastNetworkErrorMessageAt = 0;

/**
 * 获取HTTP状态码对应的错误消息
 */
const getErrorMessageByStatus = (status: number): string => {
  const statusMessages: Record<number, string> = {
    400: '请求参数错误',
    401: '未授权，请重新登录',
    403: '拒绝访问',
    404: '请求资源未找到',
    408: '请求超时',
    409: '资源冲突',
    422: '请求格式错误',
    429: '请求过于频繁，请稍后再试',
    500: '服务器内部错误',
    502: '网关错误',
    503: '服务暂时不可用',
    504: '网关超时',
  };
  return statusMessages[status] || `请求错误: ${status}`;
};

/**
 * 从错误响应中提取详细的错误信息
 */
const extractErrorDetail = (error: AxiosError): string => {
  if (error.response?.data) {
    const data = error.response.data as ErrorResponse;
    return data.detail || data.message || data.error || '';
  }
  return '';
};

/**
 * 处理HTTP错误
 */
export const handleHttpError = (
  error: AxiosError,
  config: ErrorConfig = DEFAULT_ERROR_CONFIG
): string => {
  let message = '请求失败，请稍后重试';

  if (error.response) {
    // 服务器返回了错误响应
    message = getErrorMessageByStatus(error.response.status);
    const detail = extractErrorDetail(error);
    if (detail) {
      message = detail;
    }
  } else if (error.request) {
    // 请求已发出但没有收到响应
    message = '网络连接失败，请检查网络设置';
  } else {
    // 请求配置出错
    message = error.message || '请求配置错误';
  }

  // 执行自定义错误处理器
  if (config.customHandler) {
    config.customHandler(error);
  }

  // 显示错误消息
  if (config.showMessage) {
    const isNetworkError = !error.response && Boolean(error.request);
    const now = Date.now();
    if (!isNetworkError || now - lastNetworkErrorMessageAt >= NETWORK_ERROR_MESSAGE_COOLDOWN_MS) {
      ElMessage.error(message);
      if (isNetworkError) lastNetworkErrorMessageAt = now;
    }
  }

  if (error && typeof error === 'object') handledErrors.add(error);

  return message;
};

/**
 * 创建带错误处理的请求配置
 */
export const createRequestConfig = (
  customConfig?: Partial<ErrorConfig>
): ErrorConfig => ({
  ...DEFAULT_ERROR_CONFIG,
  ...customConfig,
});

// ============================================================================
// Request/Response Interceptors
// ============================================================================

// Request Interceptor
http.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 让 Axios 根据请求体选择正确协议。特别是 FormData 必须由浏览器写入
    // multipart boundary，不能被全局 application/json 覆盖。
    if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
      config.headers.delete('Content-Type');
    }
    return applyLearnerIdentity(config);
  },
  (error: AxiosError) => {
    handleHttpError(error, { showMessage: error.config?.silentError !== true });
    return Promise.reject(error);
  }
);

// Response Interceptor
http.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  (error: AxiosError) => {
    handleHttpError(error, { showMessage: error.config?.silentError !== true });
    return Promise.reject(error);
  }
);

// ============================================================================
// Enhanced HTTP Methods with Error Handling
// ============================================================================

/**
 * 执行HTTP请求并统一处理错误
 */
export const safeRequest = async <T>(
  requestFn: () => Promise<AxiosResponse<T>>,
  errorConfig?: Partial<ErrorConfig>
): Promise<T | null> => {
  try {
    const response = await requestFn();
    return response.data;
  } catch (error) {
    const axiosError = error as AxiosError;
    if (!axiosError || typeof axiosError !== 'object' || !handledErrors.has(axiosError)) {
      handleHttpError(axiosError, createRequestConfig(errorConfig));
    }
    return null;
  }
};

export default http;
