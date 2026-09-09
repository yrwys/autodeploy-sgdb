from fastapi import FastAPI, HTTPException, status
from app.schemas import DeployDatabaseRequest, DeployDatabaseResponse, ClusterStatusResponse
from app.k8s import deploy_sg_cluster, fetch_sg_cluster_status
from kubernetes.client.exceptions import ApiException

app = FastAPI(
    title="Database Orchestration API",
    description="Internal API for 'one shot' StackGres database cluster provisioning.",
    version="1.0.0"
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post(
    "/api/v1/databases", 
    response_model=DeployDatabaseResponse, 
    status_code=status.HTTP_201_CREATED
)
def create_database(payload: DeployDatabaseRequest):
    """Triggers a one-shot deployment of a StackGres cluster."""
    try:
        deploy_sg_cluster(
            cluster_name=payload.cluster_name,
            namespace=payload.namespace,
            instances=payload.instances,
            postgres_version=payload.postgres_version,
            storage_size=payload.storage_size,
            storage_class=payload.storage_class,  # ADDED
            cpu_request=payload.cpu_request,
            memory_request=payload.memory_request
        )
    except ApiException as e:
        raise HTTPException(
            status_code=e.status,
            detail=f"Kubernetes API error: {e.reason}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

    rw_endpoint = f"{payload.cluster_name}.{payload.namespace}.svc.cluster.local:5432"
    ro_endpoint = f"{payload.cluster_name}-replicas.{payload.namespace}.svc.cluster.local:5432"

    return DeployDatabaseResponse(
        message=f"StackGres cluster '{payload.cluster_name}' provisioning initiated.",
        cluster_name=payload.cluster_name,
        namespace=payload.namespace,
        endpoints={
            "primary_rw": rw_endpoint,
            "read_replica_ro": ro_endpoint
        }
    )


@app.get(
    "/api/v1/databases/{namespace}/{cluster_name}",
    response_model=ClusterStatusResponse
)
def get_database_status(cluster_name: str, namespace: str = "default"):
    """Fetches the current StackGres CR status."""
    try:
        cluster_status = fetch_sg_cluster_status(cluster_name=cluster_name, namespace=namespace)
        return ClusterStatusResponse(
            cluster_name=cluster_name,
            namespace=namespace,
            status=cluster_status
        )
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster '{cluster_name}' not found in namespace '{namespace}'."
            )
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )