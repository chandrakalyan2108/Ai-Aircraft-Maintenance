import axios from 'axios';

// Uses environment variable if available, otherwise defaults to your active backend LoadBalancer
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://http://a838dab0db39b4f84af0264055780a1f-1662849908.us-east-1.elb.amazonaws.com';

const api = axios.create({
  baseURL: BACKEND_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;
