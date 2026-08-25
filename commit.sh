#!/bin/bash

#git add .github/workflows/was-cicd.yml
git add .github/workflows/*
git commit -m "conf cicd.yml 추가"
git push -u origin dev

#git add backend/
#git commit -m "재업로두"
#git push -u origin dev

# conf
git add conf/
git commit -m "upload additional conf"
git push -u origin dev
