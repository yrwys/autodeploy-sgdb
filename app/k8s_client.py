from kubernetes import client, config, dynamic


def get_dynamic_client() -> dynamic.DynamicClient:
    """Loads K8s config (in-cluster or local kubeconfig) and returns a DynamicClient."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    return dynamic.DynamicClient(client.ApiClient())
