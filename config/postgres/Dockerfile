FROM postgres:16

# Install pg_cron extension
RUN apt-get update && \
    apt-get install -y postgresql-16-cron && \
    rm -rf /var/lib/apt/lists/*

# Configure PostgreSQL to load pg_cron
RUN echo "shared_preload_libraries = 'pg_cron'" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "cron.database_name = 'postgres'" >> /usr/share/postgresql/postgresql.conf.sample
