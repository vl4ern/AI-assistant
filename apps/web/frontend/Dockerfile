FROM node:22-alpine

WORKDIR /app

COPY apps/web/frontend/package.json ./package.json
COPY apps/web/frontend/package-lock.json ./package-lock.json
RUN npm ci

COPY apps/web/frontend .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
