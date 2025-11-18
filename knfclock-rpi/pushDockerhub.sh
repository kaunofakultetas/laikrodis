#!/bin/bash

CONTAINER_NAME=knfclock-rpi

TODAY=$(date +%Y%m%d)
sudo docker login -u admin@knf.vu.lt
sudo docker build -t $CONTAINER_NAME .
sudo docker tag $CONTAINER_NAME vuknf/$CONTAINER_NAME:latest
sudo docker tag $CONTAINER_NAME vuknf/$CONTAINER_NAME:$TODAY
sudo docker push vuknf/$CONTAINER_NAME:latest
sudo docker push vuknf/$CONTAINER_NAME:$TODAY
