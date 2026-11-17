FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json ./
# Os scripts de instalação do baileys/protobufjs só conferem versão: pular é seguro.
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
COPY src ./src
# Sessões pareadas (segredo: dá acesso ao WhatsApp do escritório). Volume próprio.
RUN mkdir -p /data && chown node:node /data
USER node
EXPOSE 3100
CMD ["node", "src/server.js"]
