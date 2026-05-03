// JS proxy config (not JSON) so BACKEND_URL env var works in Docker Compose
const BACKEND_URL = process.env['BACKEND_URL'] || 'http://localhost:8000';

module.exports = {
  '/api': {
    target: BACKEND_URL,
    secure: false,
    changeOrigin: true,
    ws: true,
  },
};
