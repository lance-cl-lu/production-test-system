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
  startSensorTest: (data) => api.post('/api/sensor/start-test', data),
  readSensorSerial: () => api.post('/api/sensor/read-serial'),
  getLatestSensorSerial: () => api.get('/api/sensor/serial-found/latest'),
  runSensorStage: (data) => api.post('/api/sensor/run-stage', data),
  getSensorStageResult: (params) => api.get('/api/sensor/stage-result', { params }),
  reportSensorEvent: (data) => api.post('/api/sensor/events', data),
  getSensorTestRuns: (params) => api.get('/api/sensor/test-runs', { params }),
  checkSensorSerialHistory: (params) => api.get('/api/sensor/test-runs/duplicate-check', { params }),
  exportSensorTestRuns: (params) => api.get('/api/sensor/test-runs/export.csv', {
    params, responseType: 'blob', timeout: 60000,
  }),
  getSensorTestRunStats: () => api.get('/api/sensor/test-runs/stats'),
  deleteSensorTestRun: (id) => api.delete(`/api/sensor/test-runs/${id}`),
};

// Health Check
export const healthCheck = () => api.get('/health');

export default api;
