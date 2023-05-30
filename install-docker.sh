#!/bin/bash

# Commands  used in Python script

# Install docker
sudo yum update -y && sudo yum install -y docker
sudo systemctl start docker 
sudo usermod -aG docker ec2-user

