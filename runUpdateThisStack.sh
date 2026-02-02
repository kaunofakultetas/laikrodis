#!/bin/bash

mkdir -p _DATA

sudo docker-compose down
sudo docker-compose up -d --build