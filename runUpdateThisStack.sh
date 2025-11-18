#!/bin/bash

mkdir -p DATA

sudo docker-compose down
sudo docker-compose up -d --build