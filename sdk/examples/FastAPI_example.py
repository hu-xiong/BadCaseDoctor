"""
FastAPI + BadCase SDK 示例
pip install "badcase-sdk[fastapi]" 或 pip install -e ..[fastapi]
"""
from fastapi import FastAPI
import badcase_sdk

app = FastAPI()

# 一行挂载 /metrics
badcase_sdk.install(app)

@app.get("/")
def root():
    return {"message": "BadCase SDK + FastAPI"}
