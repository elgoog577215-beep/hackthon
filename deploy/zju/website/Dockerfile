FROM node:22-alpine AS builder

WORKDIR /app

ARG VITE_LINGZHI_COURSES_URL=/lingzhi/courses
ENV VITE_LINGZHI_COURSES_URL=${VITE_LINGZHI_COURSES_URL}

COPY package*.json ./

RUN npm ci

COPY . .

RUN npm run build

FROM nginx:stable-alpine

COPY nginx.conf /etc/nginx/templates/default.conf.template

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
