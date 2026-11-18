FROM python:3.12-slim

RUN useradd -m -u 1000 user \
    && mkdir -p /home/user/app/data \
    && chown -R user:user /home/user/app

WORKDIR /home/user/app

COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt huggingface_hub

COPY --chown=user:user . .

USER user
ENV PORT=7860
ENV PYTHONUNBUFFERED=1
ENV WEB_CONCURRENCY=1
ENV BOT_CONCURRENCY=1
ENV BOT_BUDGET_SCALE=0.5

EXPOSE 7860

CMD ["python", "server.py"]
