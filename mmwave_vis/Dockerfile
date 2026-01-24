#Dockerfile
ARG BUILD_FROM
FROM $BUILD_FROM

# Force Python to print logs immediately
ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache python3 py3-pip jq

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

RUN chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]