import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// Test Records API
export const testRecordsAPI = {
  getAll: (params) => api.get('/api/test-records/', { params }),
  getById: (id) => api.get(`/api/test-records/${id}`),
  create: (data) => api.post('/api/test-records/', data),
  update: (id, data) => api.put(`/api/test-records/${id}`, data),
  delete: (id) => api.delete(`/api/test-records/${id}`),
};

// Health Check
export const healthCheck = () => api.get('/health');

export default api;
