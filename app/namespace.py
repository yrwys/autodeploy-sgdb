import time
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from app.k8s_client import get_dynamic_client

OPERATOR_NAMESPACE = "stackgres"
OPERATOR_DEPLOYMENT = "stackgres-operator"
ENV_VAR_NAME = "ALLOWED_NAMESPACES"

ROLLOUT_TIMEOUT_SECONDS = 120
ROLLOUT_POLL_INTERVAL_SECONDS = 3
POST_ROLLOUT_SETTLE_SECONDS = 30

LIMITRANGE_NAME = "stackgres-default-limits"

class NamespaceNotFoundError(Exception):
    """Raised when the target namespace does not exist."""
    pass


def _namespace_exists(core_v1: client.CoreV1Api, namespace: str) -> bool:
    try:
        core_v1.read_namespace(name=namespace)
        return True
    except ApiException as e:
        if e.status == 404:
            return False
        raise

def _get_apps_v1_api() -> client.AppsV1Api:
    dyn_client = get_dynamic_client()
    return client.AppsV1Api(dyn_client.client)


def _get_core_v1_api() -> client.CoreV1Api:
    dyn_client = get_dynamic_client()
    return client.CoreV1Api(dyn_client.client)


def _get_current_allowed_namespaces(apps_v1: client.AppsV1Api) -> tuple[list[str], str]:
    deployment = apps_v1.read_namespaced_deployment(
        name=OPERATOR_DEPLOYMENT, namespace=OPERATOR_NAMESPACE
    )
    containers = deployment.spec.template.spec.containers

    for container in containers:
        env_list = container.env or []
        for env_var in env_list:
            if env_var.name == ENV_VAR_NAME:
                current = env_var.value or ""
                namespaces = [ns.strip() for ns in current.split(",") if ns.strip()]
                return namespaces, container.name

    return [], containers[0].name


def _ensure_limitrange(core_v1: client.CoreV1Api, namespace: str) -> None:
    limit_range = client.V1LimitRange(
        metadata=client.V1ObjectMeta(name=LIMITRANGE_NAME, namespace=namespace),
        spec=client.V1LimitRangeSpec(
            limits=[
                client.V1LimitRangeItem(
                    type="Container",
                    default={"cpu": "250m", "memory": "512Mi"},
                    default_request={"cpu": "100m", "memory": "128Mi"},
                )
            ]
        ),
    )
    try:
        core_v1.create_namespaced_limit_range(namespace=namespace, body=limit_range)
    except ApiException as e:
        if e.status != 409:
            raise


def ensure_namespace_allowed(namespace: str) -> bool:
    apps_v1 = _get_apps_v1_api()
    core_v1 = _get_core_v1_api()

    if not _namespace_exists(core_v1, namespace):
        raise NamespaceNotFoundError(
            f"Namespace '{namespace}' does not exist."
        )

    _ensure_limitrange(core_v1, namespace)

    current_namespaces, container_name = _get_current_allowed_namespaces(apps_v1)

    if namespace in current_namespaces:
        return False

    updated_namespaces = current_namespaces + [namespace]
    new_value = ",".join(updated_namespaces)

    patch_body = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": container_name,
                            "env": [{"name": ENV_VAR_NAME, "value": new_value}],
                        }
                    ]
                }
            }
        }
    }

    apps_v1.patch_namespaced_deployment(
        name=OPERATOR_DEPLOYMENT,
        namespace=OPERATOR_NAMESPACE,
        body=patch_body,
    )

    _wait_for_rollout(apps_v1)

    time.sleep(POST_ROLLOUT_SETTLE_SECONDS)

    return True


def _wait_for_rollout(apps_v1: client.AppsV1Api) -> None:
    deadline = time.monotonic() + ROLLOUT_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        deployment = apps_v1.read_namespaced_deployment(
            name=OPERATOR_DEPLOYMENT, namespace=OPERATOR_NAMESPACE
        )
        spec_replicas = deployment.spec.replicas or 1
        status = deployment.status

        generation_matches = (
            status.observed_generation is not None
            and status.observed_generation >= deployment.metadata.generation
        )
        replicas_ready = (
            status.updated_replicas == spec_replicas
            and status.available_replicas == spec_replicas
        )

        if generation_matches and replicas_ready:
            return

        time.sleep(ROLLOUT_POLL_INTERVAL_SECONDS)

    raise RuntimeError(
        f"stackgres-operator rollout did not complete within "
        f"{ROLLOUT_TIMEOUT_SECONDS}s after patching {ENV_VAR_NAME}"
    )