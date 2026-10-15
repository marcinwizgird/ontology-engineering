# Offline Ontop reformulation sidecar: the Ontop 5.5.0 jars from the official image plus one
# class that drives QueryReformulator directly (no JDBC connection; see OfflineReformulator.java).
FROM ontop/ontop:5.5.0 AS ontop

FROM eclipse-temurin:11-jdk AS build
COPY --from=ontop /opt/ontop/lib /ontop-lib
COPY src/OfflineReformulator.java /src/
RUN javac -cp "/ontop-lib/*" -d /classes /src/OfflineReformulator.java

FROM ontop/ontop:5.5.0
COPY --from=build /classes /opt/sidecar
COPY src/logback.xml /opt/sidecar/
ENV ONTOP_INPUT_DIR=/opt/ontop/input PORT=8080
EXPOSE 8080
ENTRYPOINT ["java", "-Xmx512m", "-Dsun.net.httpserver.nodelay=true", "-cp", "/opt/sidecar:/opt/ontop/lib/*:/opt/ontop/jdbc/*", "OfflineReformulator"]
