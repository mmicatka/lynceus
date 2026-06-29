ARG BASE_IMAGE=lynceus-base
FROM ${BASE_IMAGE}

ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid ${USER_GID} openhands \
    || groupmod -n openhands $(getent group ${USER_GID} | cut -d: -f1) \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m openhands \
    || usermod -l openhands -m -d /home/openhands $(getent passwd ${USER_UID} | cut -d: -f1) \
    && echo "openhands ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/openhands \
    && chmod 0440 /etc/sudoers.d/openhands

USER openhands
