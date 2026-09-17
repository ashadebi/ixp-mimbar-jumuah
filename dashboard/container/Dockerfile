# Source release pinned to BIRD 2.19.2, published 2026-07-30 by CZ.NIC.
# Official source: https://bird.nic.cz/get-bird/
FROM debian:bookworm-slim AS builder
ARG BIRD_VERSION=2.19.2
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl build-essential flex bison libreadline-dev libncurses-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl --fail --location --retry 3 "https://bird.nic.cz/download/bird-${BIRD_VERSION}.tar.gz" -o bird.tar.gz \
    && tar xzf bird.tar.gz --strip-components=1 \
    && ./configure --prefix=/usr --sysconfdir=/etc/bird --localstatedir=/var --disable-libssh \
    && make -j2 && make install DESTDIR=/out
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libreadline8 libtinfo6 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /out/usr/sbin/bird /usr/sbin/bird
COPY --from=builder /out/usr/sbin/birdc /usr/sbin/birdc
USER 65534:65534
ENTRYPOINT ["/usr/sbin/bird"]
CMD ["--version"]
