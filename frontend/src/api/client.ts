import axios from 'axios';

// All requests go through the Vite dev proxy at /api -> http://localhost:8000
// (see vite.config.ts). In production, set VITE_API_BASE_URL and point it
// straight at the deployed backend instead.
const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api';

export const apiClient = axios.create({ baseURL });

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// The backend doesn't expose a "when does my token expire" endpoint, so the
// only reliable signal is a 401 coming back on an actual request. When that
// happens, the token's dead — clear it and bounce to /login rather than
// showing a confusing error in place.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);
