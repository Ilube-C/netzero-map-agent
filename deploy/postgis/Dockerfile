# PostGIS for the Fly deployment. db/init.sql is baked in and runs once, when
# the volume is empty — exactly as it does under docker-compose locally.
#
# Build context is the REPO ROOT so this reads the same db/init.sql that
# docker-compose mounts, with no duplicated copy to drift:
#   flyctl deploy --config deploy/postgis/fly.toml --dockerfile deploy/postgis/Dockerfile
FROM postgis/postgis:16-3.4

COPY db/init.sql /docker-entrypoint-initdb.d/init.sql

# The Fly volume mounts at /var/lib/postgresql/data and arrives holding
# lost+found, which makes initdb refuse the directory. Keep the cluster in a
# subdirectory of the mount instead.
ENV PGDATA=/var/lib/postgresql/data/pgdata

# Fly's private network (6PN) is IPv6-only; the default IPv4 bind would leave
# the app unable to reach this machine at all.
CMD ["postgres", "-c", "listen_addresses=*"]
