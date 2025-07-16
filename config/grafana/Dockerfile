FROM grafana/grafana:latest

# Install gettext for envsubst
USER root
RUN apk add --no-cache gettext

# Copy configuration files
COPY provisioning/ /etc/grafana/provisioning/
COPY dashboards/ /etc/grafana/dashboards/
COPY init-grafana.sh /init-grafana.sh
RUN chmod +x /init-grafana.sh

# Fix permissions for grafana user (UID 472) to write to provisioning directory
RUN chown -R 472:472 /etc/grafana/provisioning/

# Switch back to grafana user
USER 472

ENTRYPOINT ["/init-grafana.sh"] 