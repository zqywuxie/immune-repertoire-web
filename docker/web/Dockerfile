FROM node:22-bookworm-slim AS test
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
CMD ["npm", "test"]

FROM test AS build
RUN npm run build

FROM nginx:1.28-alpine AS runtime
ENV UPLOAD_MAX_MB=100
COPY docker/web/default.conf /etc/nginx/templates/default.conf.template
COPY --from=build /frontend/dist /usr/share/nginx/html
EXPOSE 80
