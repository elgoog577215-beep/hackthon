import axios from 'axios';
import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { ElMessage } from 'element-plus';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

// ============================================================================
// HTTP Client Configuration
// ============================================================================

const http: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 180000, // 180 seconds for LLM operations
  headers: {
    'Content-Type': 'application/json',
  },
});

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

const DEFAULT_ERROR_CONFIG: ErrorConfig = {
  showMessage: true,
};

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
    ElMessage.error(message);
  }

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
    // 可以在这里添加认证token等
    return config;
  },
  (error: AxiosError) => {
    handleHttpError(error);
    return Promise.reject(error);
  }
);

// Response Interceptor
http.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  (error: AxiosError) => {
    handleHttpError(error);
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
    handleHttpError(axiosError, createRequestConfig(errorConfig));
    return null;
  }
};

export default http;
