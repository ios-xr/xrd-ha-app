FROM bats/bats:1.9.0

WORKDIR /chart

RUN echo "@community https://dl-cdn.alpinelinux.org/alpine/latest-stable/community" >> /etc/apk/repositories

RUN apk update && \
    apk upgrade && \
    apk add curl docker helm@community kind@community yamllint yq

RUN curl -L https://github.com/yannh/kubeconform/releases/download/v0.6.1/kubeconform-linux-amd64.tar.gz | tar -xz -C /usr/local/bin kubeconform

RUN VERSION=$(curl -L -s https://dl.k8s.io/release/stable.txt) \
    curl -o /usr/local/bin/kubectl -L "https://dl.k8s.io/release/$VERSION/bin/linux/amd64/kubectl" && \
    chmod +x /usr/local/bin/kubectl

ENTRYPOINT ["bash"]
