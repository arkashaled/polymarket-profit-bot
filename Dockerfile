FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sniper_bot.py .
COPY start_sniper.sh .
RUN chmod +x start_sniper.sh
CMD ["./start_sniper.sh"]
