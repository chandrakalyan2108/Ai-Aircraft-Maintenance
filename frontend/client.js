import axios from 'axios';

// Uses environment variable if available, otherwise defaults to your active backend LoadBalancer
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://http://VITE_BACKEND_URL=http://a78e9e9ad373f40318e1541a81f32826-2143101633.ap-south-2.elb.amazonaws.com';

const api = axios.create({
  baseURL: BACKEND_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;
