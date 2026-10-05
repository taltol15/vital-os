FROM python:3.12-slim

WORKDIR /srv
COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY server/vital_market /srv/vital_market
COPY python /srv/python
COPY schema /srv/schema
ENV PYTHONPATH=/srv:/srv/python
ENV VITAL_MARKET_SCHEMA=/srv/schema/catalog-item.schema.json
ENV VITAL_MARKET_DB=/data/market.db
ENV VITAL_MARKET_DATA=/data
EXPOSE 8080
CMD ["uvicorn", "vital_market.app:app", "--host", "0.0.0.0", "--port", "8080"]
