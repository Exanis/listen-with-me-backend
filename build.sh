#!/bin/bash

SERVICE='backend'
FRONTEND_VERSION=$(cat ../kube/FRONTEND)
BACKEND_VERSION=$(($(cat ../kube/BACKEND)+1))

docker build -t rg.fr-par.scw.cloud/listenwithme/${SERVICE}:latest -t rg.fr-par.scw.cloud/listenwithme/${SERVICE}:${BACKEND_VERSION} -t listenwithme/${SERVICE}:latest .
docker push rg.fr-par.scw.cloud/listenwithme/${SERVICE}:${BACKEND_VERSION}
docker push rg.fr-par.scw.cloud/listenwithme/${SERVICE}:latest

cat ../kube/deploy.tpl.yaml | sed "s/@@FRONTEND_VERSION@@/${FRONTEND_VERSION}/" | sed "s/@@BACKEND_VERSION@@/${BACKEND_VERSION}/" > ../kube/deploy.yaml
kubectl --kubeconfig=../kube/kubeconfig-listen-with-me.yaml apply -f ../kube/deploy.yaml
echo ${BACKEND_VERSION} > ../kube/BACKEND