// Proxy do ng serve: /api vai para o Django. No compose, API_PROXY_TARGET=http://backend:8000.
module.exports = {
  '/api': {
    target: process.env.API_PROXY_TARGET || 'http://localhost:8000',
    secure: false,
  },
};
