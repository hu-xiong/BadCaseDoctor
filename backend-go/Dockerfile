# 构建阶段
FROM golang:1.22-alpine AS builder

WORKDIR /app

# 复制依赖文件
COPY go.mod go.sum ./

# 下载依赖
RUN go mod download

# 复制源代码
COPY . .

# 构建应用
RUN CGO_ENABLED=0 GOOS=linux go build -o server ./cmd/server

# 运行阶段
FROM alpine:latest

WORKDIR /app

# 复制构建的二进制文件
COPY --from=builder /app/server .

# 复制.env文件（如果存在）
COPY .env* ./

# 暴露端口
EXPOSE 8000

# 运行应用
CMD ["./server"]