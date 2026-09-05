import axios from 'axios';
import type { AxiosInstance, AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { trackApiAction } from './usage-tracker';
import { publishAppError, toAppError } from './app-error';
import { createUuid } from './client-id';

const stripTrailingSlash = (value: string) => value.replace(/\/+$/, '');
const CONFIGURED_LEARNER_USER_ID = String(import.meta.env.VITE_LEARNER_USER_ID || '').trim();
const CONFIGURED_TEACHER_USER_ID = String(import.meta.env.VITE_TEACHER_USER_ID || '').trim();
const QIZHI_AUTH_REQUIRED = String(import.meta.env.VITE_QIZHI_AUTH_REQUIRED || '').trim() === 'true';
const QIZHI_AUTH_TOKEN_KEY = 'auth_token';
export const LEARNER_ID_STORAGE_KEY = 'lingzhi_learner_id_v1';
export const LOCAL_TEACHER_USER_ID = 'teacher-local-workbench-v1';
export type RequestIdentityScope = 'learner' | 'teacher';
let inMemoryLearnerId = '';
let activeIdentityScope: RequestIdentityScope = 'learner';

export const getQizhiAccessToken = (): string => {
  if (!QIZHI_AUTH_REQUIRED) return '';
  try {
    return String(
      localStorage.getItem(QIZHI_AUTH_TOKEN_KEY)
      || sessionStorage.getItem(QIZHI_AUTH_TOKEN_KEY)
      || '',
    ).trim().replace(/^Bearer\s+/i, '');
  } catch {
    return '';
  }
};

export const isQizhiAuthRequired = (): boolean => QIZHI_AUTH_REQUIRED;

export const redirectToQizhiLogin = (): void => {
  if (typeof window === 'undefined') return;
  const redirect = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  window.location.replace(`/auth?redirect=${encodeURIComponent(redirect)}`);
};

export const applyQizhiAuthorization = (headers: Headers): Headers => {
  const token = getQizhiAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return headers;
};

export const qizhiWebSocketProtocols = (): string[] | undefined => {
  if (!QIZHI_AUTH_REQUIRED) return undefined;
  const token = getQizhiAccessToken();
  return token ? ['lingzhi-auth-v1', `qizhi-bearer.${token}`] : ['lingzhi-auth-v1'];
};

const createLearnerId = () => {
  return `learner_${createUuid()}`;
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

/**
 * 教师工作台在本地开发时使用稳定身份，避免课程列表可见、教学日历却因
 * 浏览器随机 learner id 被隔离为空。生产构建不使用这个共享本地身份，
 * 仍沿用现有请求身份契约；待正式教师账号接入后可配置 VITE_TEACHER_USER_ID。
 */
export const getTeacherIdentity = (
  configuredUserId = CONFIGURED_TEACHER_USER_ID,
  isDevelopment = import.meta.env.DEV,
): string => {
  const normalized = configuredUserId.trim();
  if (normalized && normalized !== 'default_user') return normalized;
  if (isDevelopment) return LOCAL_TEACHER_USER_ID;
  return getLearnerIdentity();
};

/**
 * The router or a domain call owns the active request scope. HTTP must never
 * guess an actor from `window.location`: that made course creation and course
 * generation use different owners when a route was missing from the matcher.
 */
export const setActiveRequestIdentityScope = (scope: RequestIdentityScope): void => {
  activeIdentityScope = scope;
};

export const getActiveRequestIdentityScope = (): RequestIdentityScope => activeIdentityScope;

export const getIdentityForScope = (scope: RequestIdentityScope): string => (
  scope === 'teacher' ? getTeacherIdentity() : getLearnerIdentity()
);

export const getActiveRequestIdentity = (): string => getIdentityForScope(activeIdentityScope);

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
  // 具体业务域可以显式指定教师等身份；通用拦截器不得覆盖它。
  if (config.headers.has('X-User-Id')) return config;
  const normalized = userId.trim();
  if (!normalized) return config;
  config.headers.set('X-User-Id', normalized);
  return config;
};

export const identityRequestConfig = (
  scope: RequestIdentityScope,
  config: AxiosRequestConfig = {},
): AxiosRequestConfig => ({ ...config, identityScope: scope });

// Ordinary workspace reads must fail quickly and recover locally.  The global
// client keeps a long timeout for model calls, but reusing that timeout for
// course metadata made a delayed GET look like a frozen application.
export const INTERACTIVE_READ_TIMEOUT_MS = 10000;

export const identityReadRequestConfig = (
  scope: RequestIdentityScope,
  config: AxiosRequestConfig = {},
): AxiosRequestConfig => identityRequestConfig(scope, {
  timeout: INTERACTIVE_READ_TIMEOUT_MS,
  ...config,
});

export const teacherRequestConfig = (
  config: AxiosRequestConfig = {},
): AxiosRequestConfig => identityRequestConfig('teacher', config);

export const teacherReadRequestConfig = (
  config: AxiosRequestConfig = {},
): AxiosRequestConfig => identityReadRequestConfig('teacher', config);

export const learnerRequestConfig = (
  config: AxiosRequestConfig = {},
): AxiosRequestConfig => identityRequestConfig('learner', config);

export const learnerReadRequestConfig = (
  config: AxiosRequestConfig = {},
): AxiosRequestConfig => identityReadRequestConfig('learner', config);

export const teacherIdentityHeaders = (
  initial: HeadersInit = {},
  userId = getTeacherIdentity(),
): Headers => {
  const headers = new Headers(initial);
  const normalized = userId.trim();
  if (normalized) headers.set('X-User-Id', normalized);
  return applyQizhiAuthorization(headers);
};

export const learnerIdentityHeaders = (
  initial: HeadersInit = {},
  userId = getLearnerIdentity(),
): Headers => {
  const headers = new Headers(initial);
  const normalized = userId.trim();
  if (normalized) headers.set('X-User-Id', normalized);
  return applyQizhiAuthorization(headers);
};

/**
 * 原生 fetch 请求必须和 Axios 拦截器使用同一页面身份。教师工作台与
 * teacherPreview 会切到教师身份，普通学习界面则继续使用独立学习者身份。
 */
export const identityScopeHeaders = (
  scope: RequestIdentityScope,
  initial: HeadersInit = {},
): Headers => scope === 'teacher'
  ? teacherIdentityHeaders(initial)
  : learnerIdentityHeaders(initial);

export const activeIdentityHeaders = (
  initial: HeadersInit = {},
): Headers => identityScopeHeaders(activeIdentityScope, initial);

// ============================================================================
// Error Handling Utilities
// ============================================================================

interface ErrorResponse {
  detail?: string | { message?: string; code?: string };
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
    usageStartedAt?: number;
    identityScope?: RequestIdentityScope;
    errorTitle?: string;
    errorSummary?: string;
  }

  export interface InternalAxiosRequestConfig {
    silentError?: boolean;
    usageStartedAt?: number;
    identityScope?: RequestIdentityScope;
    errorTitle?: string;
    errorSummary?: string;
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
    if (typeof data.detail === 'string') return data.detail;
    if (data.detail && typeof data.detail === 'object') {
      return String(data.detail.message || data.detail.code || '');
    }
    return data.message || data.error || '';
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
  const fallback = error.response
    ? extractErrorDetail(error) || getErrorMessageByStatus(error.response.status)
    : error.request
      ? '网络连接失败，请检查网络设置'
      : error.message || '请求配置错误';
  const presentation = toAppError(error, { fallback });

  // 执行自定义错误处理器
  if (config.customHandler) {
    config.customHandler(error);
  }

  // 普通用户操作统一进入结构化错误反馈层；后台静默请求继续由所属区域处理。
  if (config.showMessage) {
    const isNetworkError = !error.response && Boolean(error.request);
    const now = Date.now();
    if (!isNetworkError || now - lastNetworkErrorMessageAt >= NETWORK_ERROR_MESSAGE_COOLDOWN_MS) {
      publishAppError(error, { fallback });
      if (isNetworkError) lastNetworkErrorMessageAt = now;
    }
  }

  if (error && typeof error === 'object') handledErrors.add(error);

  return presentation.summary;
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
    config.usageStartedAt = typeof performance === 'undefined' ? Date.now() : performance.now();
    const token = getQizhiAccessToken();
    if (token) config.headers.set('Authorization', `Bearer ${token}`);
    return applyLearnerIdentity(
      config,
      getIdentityForScope(config.identityScope || activeIdentityScope),
    );
  },
  (error: AxiosError) => {
    handleHttpError(error, { showMessage: error.config?.silentError !== true });
    return Promise.reject(error);
  }
);

// Response Interceptor
http.interceptors.response.use(
  (response: AxiosResponse) => {
    const startedAt = response.config.usageStartedAt;
    const now = typeof performance === 'undefined' ? Date.now() : performance.now();
    trackApiAction({
      method: response.config.method,
      url: response.config.url,
      statusCode: response.status,
      durationMs: startedAt === undefined ? 0 : now - startedAt,
      userId: String(response.config.headers?.get?.('X-User-Id') || ''),
    });
    return response;
  },
  (error: AxiosError) => {
    const startedAt = error.config?.usageStartedAt;
    const now = typeof performance === 'undefined' ? Date.now() : performance.now();
    trackApiAction({
      method: error.config?.method,
      url: error.config?.url,
      statusCode: error.response?.status || 0,
      durationMs: startedAt === undefined ? 0 : now - startedAt,
      userId: String(error.config?.headers?.get?.('X-User-Id') || ''),
    });
    if (QIZHI_AUTH_REQUIRED && error.response?.status === 401) {
      redirectToQizhiLogin();
    }
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
