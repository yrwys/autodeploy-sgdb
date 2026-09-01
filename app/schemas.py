from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class DeployDatabaseRequest(BaseModel):
    cluster_name: str = Field(
        ..., 
        description="Name of the StackGres cluster (must be valid K8s resource name)",
        example="billing-db"
    )
    namespace: str = Field(
        default="default", 
        description="Target Kubernetes namespace",
        example="default"
    )
    instances: int = Field(
        default=2, 
        ge=1, 
        le=10, 
        description="Number of DB instances (2 = 1 primary + 1 replica)",
        example=2
    )
    postgres_version: str = Field(
        default="15", 
        description="PostgreSQL major version (e.g., '14', '15', '16')",
        example="15"
    )
    storage_size: str = Field(
        default="10Gi", 
        description="PVC storage size",
        example="20Gi"
    )
    # UPDATED: Raised baseline defaults so patroni receives valid resource limits
    cpu_request: str = Field(
        default="1000m",
        description="CPU allocation per instance (e.g., '500m', '1000m', '2000m')",
        example="1000m"
    )
    memory_request: str = Field(
        default="1Gi",
        description="Memory allocation per instance (e.g., '1Gi', '2Gi')",
        example="1Gi"
    )

class DeployDatabaseResponse(BaseModel):
    message: str
    cluster_name: str
    namespace: str
    endpoints: Dict[str, str]

class ClusterStatusResponse(BaseModel):
    cluster_name: str
    namespace: str
    status: Optional[Dict[str, Any]] = None