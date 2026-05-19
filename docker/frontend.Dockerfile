# ATRIO Frontend — build SPA, serve via Caddy.

# ----- Stage 1: build -----
FROM node:20-alpine AS build

WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ----- Stage 2: serve -----
FROM caddy:2.8-alpine AS serve

COPY --from=build /build/dist /srv

EXPOSE 80

# Caddyfile mounted at runtime via volume in docker-compose.
