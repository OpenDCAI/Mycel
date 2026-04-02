FROM node:20-alpine AS builder

# Build-time API base URL (e.g. https://api.mycel.nextmind.space).
# Coolify passes this via --build-arg; Vite bakes it into the bundle.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
