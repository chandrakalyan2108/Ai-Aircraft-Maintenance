import axios from 'axios';

const api = axios.create({
  baseURL: 'http://a78e9e9ad373f40318e1541a81f32826-2143101633.ap-south-2.elb.amazonaws.com',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;
