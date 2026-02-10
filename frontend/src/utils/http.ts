import axios from 'axios';
import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { ElMessage } from 'element-plus';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const http: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 180000, // 180 seconds for LLM operations
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor
http.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

interface ErrorResponse {
  detail?: string;
}

// Response Interceptor
http.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  (error: AxiosError) => {
    let message = '请求失败，请稍后重试';
    
    if (error.response) {
      switch (error.response.status) {
        case 400:
          message = '请求参数错误';
          break;
        case 401:
          message = '未授权，请重新登录';
          break;
        case 403:
          message = '拒绝访问';
          break;
        case 404:
          message = '请求资源未找到';
          break;
        case 500:
          message = '服务器内部错误';
          break;
        default:
          message = `请求错误: ${error.response.status}`;
      }
      
      // If backend returns a specific detail message, use it
      const data = error.response.data as ErrorResponse;
      if (data && data.detail) {
        message = data.detail;
      }
    } else if (error.request) {
      message = '网络连接失败，请检查网络设置';
    } else {
      message = error.message;
    }

    ElMessage.error(message);
    return Promise.reject(error);
  }
);

export default http;
