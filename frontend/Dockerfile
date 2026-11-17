# Build do Angular e servidor web (Caddy): arquivos estáticos + proxy para o backend + HTTPS.
FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx ng build --configuration production

FROM caddy:2.10-alpine
COPY --from=build /app/dist/frontend/browser /srv
