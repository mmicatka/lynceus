# modules/local/docking/Dockerfile
#
# Targets:
#   cpu -> AutoDock Vina (PyPI `vina` bindings)
#   gpu -> Vina-GPU 2.1 (source build), requires nvidia-container-toolkit
#          at `docker run` time
#
# FIXME: targets OpenCL via Vina-GPU 2.1, not CUDA-native Vina-CUDA.
# Revisit if NVIDIA-only lock-in becomes acceptable.
#
# Build:
#   docker build --target cpu -t lynceus/docking:cpu-0.1.0 modules/local/docking
#   docker build --target gpu -t lynceus/docking:gpu-0.1.0 modules/local/docking


# -----------------------------------------------------------------------------
# vina-gpu-builder: compile Vina-GPU 2.1. Separate base image from the final
# stages because compiling requires the CUDA/OpenCL devel toolchain, which
# has no equivalent in python:3.12-slim-trixie and shouldn't ship in the
# runtime image regardless.
# -----------------------------------------------------------------------------
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS vina-gpu-builder

ARG VINA_GPU_REPO=https://github.com/DeltaGroupNJUPT/Vina-GPU-2.1.git
ARG VINA_GPU_REF=main
# Per the upstream README's options table, this must be the FULL
# preprocessor flag (-DNVIDIA_PLATFORM / -DAMD_PLATFORM), not a bare
# vendor name — the Makefile substitutes this value directly onto the
# gcc/ld command line unflagged, so a bare "Nvidia" becomes a bogus
# positional link argument ("ld: cannot find Nvidia").
ARG GPU_PLATFORM=-DNVIDIA_PLATFORM
ARG BOOST_VERSION=1.83.0

RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  git \
  wget \
  ocl-icd-opencl-dev \
  ocl-icd-libopencl1 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/boost-src
RUN BOOST_UNDERSCORE=$(echo "${BOOST_VERSION}" | tr '.' '_') \
  && wget -q "https://archives.boost.io/release/${BOOST_VERSION}/source/boost_${BOOST_UNDERSCORE}.tar.gz" \
  && tar -xzf "boost_${BOOST_UNDERSCORE}.tar.gz" \
  && mv "boost_${BOOST_UNDERSCORE}" /opt/boost \
  && rm -rf /opt/boost-src

# The Makefile links against -lboost_program_options, -lboost_system, and
# -lboost_filesystem from $(BOOST_LIB_PATH)/stage/lib — these are compiled
# libraries, not header-only Boost, so the source tarball above is not
# sufficient on its own. Bootstrap + b2 must actually build them before
# the vina-gpu `make` step runs, or linking fails with "cannot find -l...".
#
# link=static ONLY (not static,shared): building both produces .so files
# that the linker prefers over .a for -lboost_* by default, which means
# the final binary ends up dynamically linked against Boost. The runtime
# image only copies the vina-gpu method directory, not Boost's stage/lib,
# so a dynamically-linked binary fails at container run time with
# "error while loading shared libraries: libboost_*.so.*: cannot open
# shared object file" (exit 127) — confirmed the hard way, not guessed.
# Static linking bakes Boost into the binary and avoids this entirely.
WORKDIR /opt/boost
RUN ./bootstrap.sh --with-libraries=program_options,system,filesystem,thread \
  && ./b2 -j"$(nproc)" link=static

WORKDIR /opt/vina-gpu
RUN git clone --depth 1 --branch "${VINA_GPU_REF}" "${VINA_GPU_REPO}" .

# The repo has no top-level Makefile. Per the upstream README's own build
# steps ("cd into one of the three methods of Vina-GPU 2.1"), each variant
# (AutoDock-Vina-GPU-2.1, QuickVina2-GPU-2.1, QuickVina-W-GPU-2.1) has its
# own subdirectory containing its own Makefile. We build the AutoDock-Vina
# variant specifically, since that's the one that matches CPU-target Vina
# for consistency across backends.
#
# Confirmed directory/binary naming from a real HPC install writeup
# (not guessed): the subdir is `AutoDock-Vina-GPU-2.1`, and `make` there
# produces a binary named `AutoDock-Vina-GPU-2-1` (hyphen, not a `.1`) —
# these two names genuinely differ and both must be gotten right.
#
# FIXME: this Makefile is not written for portable builds — several of
# its variables default to the original maintainer's own machine paths
# rather than anything derived from $(CURDIR)/pwd. Every one of these
# has to be found and overridden explicitly; there is no guarantee this
# is now the complete list versus what a future upstream change adds.
ARG VINA_GPU_METHOD_DIR=AutoDock-Vina-GPU-2.1
ARG VINA_GPU_BINARY_NAME=AutoDock-Vina-GPU-2-1
WORKDIR /opt/vina-gpu/${VINA_GPU_METHOD_DIR}

# Upstream Makefile hardcodes these as in-file variables rather than
# make-arguments; overriding via `make VAR=value` keeps the actual build
# inputs visible here instead of requiring an in-place Makefile edit.
#
# WORK_DIR is the critical one and easy to miss: it defaults to the
# original maintainer's own dev-machine path (checked into version
# control) and is used to build the -I include paths for the project's
# OWN headers (lib/, OpenCL/inc/) — not just Boost/OpenCL system paths.
# Omitting it compiles fine (no error) but fails at the #include step
# with "No such file or directory" for headers like commonMacros.h,
# parse_pdbqt.h, wrapcl.h, because gcc is looking in someone else's
# home directory. Confirmed via a real HPC install writeup, not guessed.
#
# OPENCL_VERSION also needs an explicit override: the Makefile's own
# default is -DOPENCL_2_0, but the README explicitly recommends
# -DOPENCL_3_0 on Linux and warns against non-3.0. Setting this
# preemptively rather than waiting to hit it as the next build failure.
RUN make \
  WORK_DIR="$(pwd)" \
  BOOST_LIB_PATH=/opt/boost \
  BOOST_INCLUDE_PATH=/opt/boost \
  OPENCL_INCLUDE_PATH=/usr/include \
  OPENCL_LIB_PATH=/usr/lib/x86_64-linux-gnu \
  OPENCL_VERSION=-DOPENCL_3_0 \
  GPU_PLATFORM="${GPU_PLATFORM}" \
  && test -x "./${VINA_GPU_BINARY_NAME}"

# Vina-GPU 2.1 also needs its precompiled/on-the-fly-compiled OpenCL kernel
# binaries (Kernel1_Opt.bin / Kernel2_Opt.bin) at runtime, alongside the
# executable — --opencl_binary_path in the config must point at wherever
# these land, so the whole method directory (not just the binary) is
# staged forward.
RUN mkdir -p /opt/vina-gpu-dist \
  && cp -r . /opt/vina-gpu-dist/ \
  && ln -s "/opt/vina-gpu-dist/${VINA_GPU_BINARY_NAME}" /opt/vina-gpu-dist/Vina-GPU


# -----------------------------------------------------------------------------
# cpu: matches the established single-stage module pattern exactly.
# -----------------------------------------------------------------------------
FROM python:3.12-slim-trixie AS cpu

RUN apt-get update && apt-get install -y --no-install-recommends \
  procps \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN uv pip install --system .

ENTRYPOINT []


# -----------------------------------------------------------------------------
# gpu: same install pattern as `cpu`, plus the compiled Vina-GPU binary and
# the NVIDIA OpenCL runtime bits needed to execute it.
# -----------------------------------------------------------------------------
FROM python:3.12-slim-trixie AS gpu

RUN apt-get update && apt-get install -y --no-install-recommends \
  procps \
  ocl-icd-libopencl1 \
  clinfo \
  && rm -rf /var/lib/apt/lists/*

# ocl-icd-libopencl1 is only the ICD LOADER — it needs an ICD file telling
# it which vendor library to dlopen(). `--gpus all` (via nvidia-container-
# runtime) mounts NVIDIA's actual OpenCL driver library into the container
# at runtime (confirmed present at
# /usr/lib/x86_64-linux-gnu/libnvidia-opencl.so.1), but does NOT create
# the /etc/OpenCL/vendors/*.icd registration file pointing the loader at
# it. Without this file the loader finds zero platforms and Vina-GPU
# fails at runtime with "Err-1001:CL_PLATFORM_NOT_FOUND_KHR" — even
# though the driver library is right there on disk. Confirmed via
# `clinfo`/`find` inside the running container, not guessed.
RUN mkdir -p /etc/OpenCL/vendors \
  && echo "libnvidia-opencl.so.1" > /etc/OpenCL/vendors/nvidia.icd

COPY --from=ghcr.io/astral-sh/uv:0.11.28-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN uv pip install --system .

COPY --from=vina-gpu-builder /opt/vina-gpu-dist/ /opt/vina-gpu/
ENV PATH="/opt/vina-gpu:${PATH}"
# `Vina-GPU` is a symlink to the real binary (AutoDock-Vina-GPU-2-1) so
# call sites don't need to hardcode the upstream project's naming.
ENV LYNCEUS_VINA_GPU_BIN=/opt/vina-gpu/Vina-GPU
# Vina-GPU 2.1's --opencl_binary_path arg must point here too, since the
# kernel .bin files live alongside the executable, not in a separate path.
ENV LYNCEUS_VINA_GPU_OPENCL_BINARY_PATH=/opt/vina-gpu
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

ENTRYPOINT []
