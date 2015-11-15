FROM centos:7

RUN \
  yum -y install gcc gcc-c++ make flex bison gperf ruby \
  openssl-devel freetype-devel fontconfig-devel libicu-devel sqlite-devel \
  libpng-devel libjpeg-devel

RUN \
  yum -y install git && \
  git clone https://github.com/ariya/phantomjs.git && \
  cd phantomjs && git checkout 2.0 && ./build.sh --confirm --jobs 1 

RUN \
  yum install -y epel-release && \
  yum install -y git python-pip python-devel && \
  pip install Django==1.8.6 && \
  pip install Pillow pika

RUN \
  yum -y install fontconfig libfontenc fontconfig-devel \
  libXfont ghostscript-fonts xorg-x11-font-utils urw-fonts

RUN \
  git clone https://github.com/ukwa/django-phantomjs.git

COPY settings.py /django-phantomjs/phantomjs/

WORKDIR django-phantomjs

RUN \
  python manage.py migrate

EXPOSE 8000

CMD python manage.py runserver 0.0.0.0:8000
