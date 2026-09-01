from kubernetes import client, config, dynamic
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic.exceptions import ResourceNotFoundError


def get_dynamic_client() -> dynamic.DynamicClient:
    """Loads K8s config (in-cluster or local kubeconfig) and returns a DynamicClient."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    return dynamic.DynamicClient(client.ApiClient())


def create_instance_profile(
    profile_name: str, namespace: str, cpu: str, memory: str
) -> str:
    dyn_client = get_dynamic_client()

    # 1. Standardize on stackgres.io/v1
    profile_api = dyn_client.resources.get(
        api_version="stackgres.io/v1", kind="SGInstanceProfile"
    )

    # 2. Structure CPU and memory under both requests and limits
    profile_manifest = {
        "apiVersion": "stackgres.io/v1",
        "kind": "SGInstanceProfile",
        "metadata": {"name": profile_name, "namespace": namespace},
        "spec": {
            "cpu": cpu,
            "memory": memory,
            "requests": {"cpu": cpu, "memory": memory},
            "limits": {"cpu": cpu, "memory": memory},
        },
    }

    try:
        profile_api.create(body=profile_manifest, namespace=namespace)
    except ApiException as e:
        if e.status == 409:
            profile_api.patch(
                name=profile_name,
                namespace=namespace,
                body=profile_manifest,
                content_type="application/merge-patch+json",
            )
        else:
            raise e

    return profile_name


def create_sg_external_service(
    cluster_name: str, namespace: str = "default", external_ip: str = None
) -> dict:
    """Creates or updates a ClusterIP Service pointing directly to the Patroni master pod."""
    dyn_client = get_dynamic_client()
    core_v1_api = client.CoreV1Api(dyn_client.client)

    service_name = f"{cluster_name}-external"

    spec = client.V1ServiceSpec(
        type="ClusterIP",
        selector={"role": "primary", "stackgres.io/cluster-name": cluster_name},
        ports=[
            client.V1ServicePort(
                name="pgsql", port=5432, target_port=5432, protocol="TCP"
            )
        ],
    )

    if external_ip:
        spec.external_ips = [external_ip]

    service_body = client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=client.V1ObjectMeta(
            name=service_name,
            namespace=namespace,
            labels={
                "purpose": "external-primary-access",
                "stackgres.io/cluster-name": cluster_name,
                "app.kubernetes.io/managed-by": "internal-orchestration-api",
            },
        ),
        spec=spec,
    )

    try:
        created_svc = core_v1_api.create_namespaced_service(
            namespace=namespace, body=service_body
        )
        return {"name": created_svc.metadata.name, "status": "created"}
    except ApiException as e:
        if e.status == 409:
            # Service already exists; patch spec to ensure selectors/externalIP match desired state
            patched_svc = core_v1_api.patch_namespaced_service(
                name=service_name, namespace=namespace, body=service_body
            )
            return {"name": patched_svc.metadata.name, "status": "patched"}
        else:
            raise e


def deploy_sg_cluster(
    cluster_name: str,
    namespace: str = "default",
    instances: int = 2,
    postgres_version: str = "15",
    storage_size: str = "10Gi",
    cpu_request: str = "500m",
    memory_request: str = "512Mi",
    external_ip: str = None,
) -> dict:
    dyn_client = get_dynamic_client()

    try:
        sg_cluster_api = dyn_client.resources.get(
            api_version="stackgres.io/v1", kind="SGCluster"
        )
    except ResourceNotFoundError:
        raise RuntimeError(
            "StackGres CRD 'SGCluster' is not installed on this cluster."
        )

    # 1. Create/Ensure the SGInstanceProfile exists with your desired CPU & Memory specs
    profile_name = f"{cluster_name}-custom-profile"
    create_instance_profile(
        profile_name=profile_name,
        namespace=namespace,
        cpu=cpu_request,
        memory=memory_request,
    )

    # 2. Create/Ensure the custom primary Service exists (e.g. test-sgdb-external)
    external_svc_info = create_sg_external_service(
        cluster_name=cluster_name,
        namespace=namespace,
        external_ip=external_ip,
    )

    # 3. Reference the profile in the SGCluster CRD
    manifest = {
        "apiVersion": "stackgres.io/v1",
        "kind": "SGCluster",
        "metadata": {
            "name": cluster_name,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/managed-by": "internal-orchestration-api"
            },
        },
        "spec": {
            "instances": instances,
            "postgres": {"version": postgres_version},
            "sgInstanceProfile": profile_name,
            "pods": {"persistentVolume": {"size": storage_size}},
        },
    }

    try:
        created_resource = sg_cluster_api.create(
            body=manifest, namespace=namespace
        )
        res_dict = created_resource.to_dict()
    except ApiException as e:
        if e.status == 409:
            patched_resource = sg_cluster_api.patch(
                name=cluster_name,
                namespace=namespace,
                body=manifest,
                content_type="application/merge-patch+json",
            )
            res_dict = patched_resource.to_dict()
        else:
            raise e

    res_dict["externalService"] = external_svc_info
    return res_dict


def fetch_sg_cluster_status(
    cluster_name: str, namespace: str = "default"
) -> dict:
    dyn_client = get_dynamic_client()

    try:
        sg_cluster_api = dyn_client.resources.get(
            api_version="stackgres.io/v1", kind="SGCluster"
        )
    except ResourceNotFoundError:
        raise RuntimeError(
            "StackGres CRD 'SGCluster' (stackgres.io/v1) is not installed on this cluster."
        )

    cluster = sg_cluster_api.get(name=cluster_name, namespace=namespace)

    cluster_dict = cluster.to_dict()
    return cluster_dict.get("status", {})