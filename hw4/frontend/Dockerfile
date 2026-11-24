# Two-stage build: the React app is compiled with Node, the result is served by nginx.
# The final image contains only nginx and the static files — no Node, no sources.

# ---- stage 1: build ----------------------------------------------------------
ARG NODE_VERSION=22
FROM node:${NODE_VERSION}-alpine AS build
WORKDIR /app

# Dependencies first: this layer is rebuilt only when package*.json change
COPY package.json package-lock.json ./
RUN npm ci

# Sources (filtered by .dockerignore), then the production build into /app/dist
COPY . .
# VITE_API_URL is baked into the bundle at build time. Empty (default) = same-origin
# "/api/..." calls that nginx proxies to the backend; set it to call the API directly.
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# ---- stage 2: serve ----------------------------------------------------------
FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
