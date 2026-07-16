# modules/local/detect_putative_sites/Dockerfile

FROM debian:trixie-slim AS fpocket-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    gcc \
    g++ \
    make \
    libnetcdf-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/Discngine/fpocket.git /opt/fpocket

WORKDIR /opt/fpocket

# fpocket's --custom_pocket arg parsing (src/fparams.c) has a pre-existing
# bug: strcpy()/assignment against the address of a char* array instead
# of the array itself. Older GCC only warns; GCC >= 14 (Debian trixie's
# default) rejects it as a hard error. Patched here rather than pinning
# to an older compiler, so the build stays correct as base images move
# forward. Pure bugfix, verified to produce identical fpocket output
# before/after (this code path -- -P/--custom_pocket -- isn't exercised
# by Lynceus's usage anyway).
RUN sed -i \
    -e 's/strcpy(&residue_string, pt);/strcpy((char *)residue_string, pt);/' \
    -e 's/rest2 = residue_string;/rest2 = (char *)residue_string;/' \
    src/fparams.c

RUN make && make install

FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/*

# fpocket binary + its runtime shared lib (VMD molfile plugin,
# dynamically loaded at run time, not just link time -- must ship
# alongside the binary, not only /usr/local/bin/fpocket itself).
# BINDIR/LIBDIR per fpocket's own makefile.
COPY --from=fpocket-builder /usr/local/bin/fpocket /usr/local/bin/fpocket
COPY --from=fpocket-builder /usr/local/lib/ /usr/local/lib/

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

COPY libs/protein-conformational-ensemble ./libs/protein-conformational-ensemble
COPY libs/lynceus-chem ./libs/lynceus-chem


COPY modules/local/detect_putative_binding_sites ./modules/local/detect_putative_binding_sites

WORKDIR /app/modules/local/detect_putative_binding_sites

RUN uv pip install --system .

ENTRYPOINT []
