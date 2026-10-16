# =============================================================================
# Frontend Dockerfile — 3-stage Next.js standalone build
# Final image: node:20-alpine (~200MB)
# =============================================================================

# Stage 1: Install dependencies (cached layer)
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts

# Stage 2: Build the application
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules

# Copy only source files (NOT node_modules — already from deps stage)
COPY package.json ./
COPY next.config.js postcss.config.js tailwind.config.js tsconfig.json ./
COPY src/ ./src/
COPY public/ ./public/
COPY messages/ ./messages/

# Build arguments for runtime config
ARG API_URL=http://localhost:8000
ARG BRAND_NAME=PrevaIQ
ENV API_URL=$API_URL
ENV NEXT_PUBLIC_BRAND_NAME=$BRAND_NAME
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# Stage 3: Production runtime (standalone output)
FROM node:20-alpine AS runner

WORKDIR /app

ARG API_URL=http://localhost:8000
ARG BRAND_NAME=PrevaIQ
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    API_URL=$API_URL \
    NEXT_PUBLIC_BRAND_NAME=$BRAND_NAME

# Non-root user for security
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy standalone output + static assets + public
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
