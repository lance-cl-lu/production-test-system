# Build stage
FROM node:18-alpine as builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

# Runtime stage
FROM node:18-alpine

WORKDIR /app

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package*.json ./

COPY public ./public
COPY src ./src

EXPOSE 3000

CMD ["npm", "start"]
