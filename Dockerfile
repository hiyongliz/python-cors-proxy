FROM registry.cn-shenzhen.aliyuncs.com/lazylibrary/python:3.13-slim
COPY --from=harbor.sunhongs.com/library/uv:0.6.17 /uv /uvx /bin/

WORKDIR /app
COPY . /app
RUN uv sync -i https://pypi.tuna.tsinghua.edu.cn/simple

CMD ["uv", "run", "main.py"]
