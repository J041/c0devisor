FROM ubuntu:latest
ENV TZ=Asia/Singapore
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone


# Do the usual updates, install python and pip, install php-cli and php

RUN apt-get update && \
    apt-get install -y \
        php \
        php-cli \
        php-dev \
        git \
        python3 \
        python3-pip \
        graphviz \
        redis

# Clone, install and make PHP-vld repo

RUN git clone https://github.com/derickr/vld.git && cd vld && \
    phpize && ./configure && \
    make && make install

# Editing config to allow for debuging and dumping of opcode

RUN echo "[vld]\n\
extension=vld.so\n\
vld.active=1\n\
vld.skip_prepend=1\n\ 
vld.skip_append=1 " >> /etc/php/8.1/cli/php.ini

WORKDIR /app

# Installing requirements with pip
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# Edit of python package source files
RUN sed '172d;240d' -i /usr/local/lib/python3.10/dist-packages/pyvis/templates/template.html
RUN sed -i "105i \ \ \ \ return quote(identifier)\n" /usr/local/lib/python3.10/dist-packages/graphviz/quoting.py

ENTRYPOINT ["/bin/bash"]
CMD ["-c", "rq worker-pool high medium low -n 3 & redis-server --daemonize yes && /bin/bash"] 
EXPOSE 5000