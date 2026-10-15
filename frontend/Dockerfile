# Next.js standalone server. Build: docker build -t abos-web frontend
# Runtime: ABOS_API_ORIGIN (where /api/* is proxied, e.g. http://api:8470) is read at build time by next.config.ts
# rewrites, so pass it as a build arg.
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-slim AS build
ARG ABOS_API_ORIGIN=http://api:8470
ENV ABOS_API_ORIGIN=${ABOS_API_ORIGIN} NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3470 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3470
CMD ["node", "server.js"]
