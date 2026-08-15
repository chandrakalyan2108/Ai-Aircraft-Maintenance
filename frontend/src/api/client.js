import axios from 'axios';
const BACKEND_URL = '/api';
const apiClient = axios.create({
  baseURL: BACKEND_URL,
});
export const healthCheck = async () => {
  const response = await apiClient.get('/health');
  return response.data;
};
export const getMaintenanceRecommendation = async (formData) => {
  const response = await apiClient.post('/recommendation', formData);
  return response.data;
};
export const uploadAnalyticsFile = async (formData) => {
  const response = await apiClient.post('/aircraft/analytics', formData);
  return response.data;
};
export default apiClient;
