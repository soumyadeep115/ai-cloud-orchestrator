To check docker containers:
docker ps

To permanently delete docker container along with database:
docker compose down -v

To stop docker container but not delete it permanently:
docker compose down

To start docker container again:
docker compose up -d


If a Kind cluster gives a TLS "certificate signed by unknown authority" error
even though the certificate isn't expired/invalid/broken then do this:

1. docker restart cluster-a-control-plane
2. Wait ~30-60 sec
3. kubectl --context kind-cluster-a get nodes

(Do the same for other clusters)

If step 3 still errors (e.g. "Forbidden: unknown"), the API server was
mid-restart — just repeat steps 1-3 once more. It should come back clean
on the second pass.


To run backend:
cd backend
uvicorn app.main:app --reload

Check cluster a:
kubectl --context kind-cluster-a -n monitoring port-forward svc/prometheus-server 9090:80

Check Cluster b:
kubectl --context kind-cluster-b -n monitoring port-forward svc/prometheus-server 9091:80