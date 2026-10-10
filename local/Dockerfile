FROM node:24-bookworm-slim AS frontend
WORKDIR /frontend
COPY tcms/package.json tcms/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tcms/ ./
RUN ./node_modules/.bin/webpack --mode production

FROM python:3.12-slim-bookworm AS python-deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config default-libmysqlclient-dev libjpeg62-turbo-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"
COPY requirements/ /requirements/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /requirements/mariadb.txt

FROM python:3.12-slim-bookworm AS app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gettext libmariadb3 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=tcms.settings.product
COPY --from=python-deps /venv/ /venv/
WORKDIR /Kiwi
COPY . .
COPY --from=frontend /frontend/node_modules/ ./tcms/node_modules/
COPY --from=frontend /frontend/static/js/bundle.js ./tcms/static/js/bundle.js
COPY local/settings.py ./tcms_settings_dir/local.py
RUN python manage.py compilemessages \
    && python manage.py collectstatic --noinput \
    && useradd --uid 1001 --create-home kiwi \
    && mkdir -p /Kiwi/uploads \
    && chown -R kiwi:kiwi /Kiwi/uploads
USER kiwi
EXPOSE 8000
CMD ["python", "local/bootstrap.py"]

FROM app AS tests
USER root
RUN pip install --no-cache-dir factory_boy parameterized textdistance tcms-api coverage
USER kiwi
