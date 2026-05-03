# Build context must be the repo root so nginx.conf is in scope.
# Set in docker-compose.prod.yml:
#   build:
#     context: .
#     dockerfile: dashboard/Dockerfile

# Stage 1 — build the Angular app
FROM node:20-alpine AS builder

WORKDIR /app

COPY dashboard/package*.json ./
RUN npm install --prefer-offline

COPY dashboard/ ./
RUN npm run build

# Stage 2 — serve with nginx
FROM nginx:1.27-alpine

COPY --from=builder /app/dist/dashboard  /usr/share/nginx/html
COPY nginx.conf                          /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
