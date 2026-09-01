import os
import streamlit as st
import requests
import pandas as pd

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/v1/databases")

st.title("Database Provisioning Portal")
st.markdown("Request a new isolated StackGres database cluster.")

# Form to create a new cluster
with st.form("deploy_db"):
    col1, col2 = st.columns(2)
    with col1:
        cluster_name = st.text_input("Cluster Name", value="tenant-db")
        postgres_version = st.selectbox("PostgreSQL Version", ["16", "15", "14", "13"], index=0)
        cpu_alloc = st.selectbox("CPU Allocation", ["500m", "1000m", "2000m", "4000m"], index=0)
    
    with col2:
        namespace = st.text_input("Namespace", value="default")
        instances = st.slider("Total Instances (includes 1 Primary)", min_value=1, max_value=5, value=2)
        memory_alloc = st.selectbox("Memory Allocation", ["512Mi", "1Gi", "2Gi", "4Gi", "8Gi"], index=0)

    storage = st.selectbox("Storage Size", ["10Gi", "20Gi", "50Gi", "100Gi"])
    
    submitted = st.form_submit_button("Deploy Cluster")

if submitted:
    # Extract clean CPU value (e.g. '1000m (1 CPU)' -> '1000m')
    clean_cpu = cpu_alloc.split()[0]

    payload = {
        "cluster_name": cluster_name,
        "namespace": namespace,
        "instances": instances,
        "postgres_version": postgres_version,
        "storage_size": storage,
        "cpu_request": clean_cpu,
        "memory_request": memory_alloc
    }
    with st.spinner(f"Provisioning {cluster_name}..."):
        response = requests.post(API_URL, json=payload)
        
        if response.status_code == 201:
            st.success("Cluster provisioning initiated successfully!")
            data = response.json()
            st.code(f"Primary Endpoint: {data['endpoints']['primary_rw']}")
        else:
            st.error(f"Error: {response.text}")

# Section to check status
st.divider()
st.subheader("Check Cluster Status")
check_col1, check_col2 = st.columns(2)
with check_col1:
    check_name = st.text_input("Cluster Name to check")
with check_col2:
    check_ns = st.text_input("Namespace to check", value="default")

def render_cluster_dashboard(status_dict: dict, cluster_name: str, namespace: str):
    if not status_dict:
        st.info("Cluster has been created but status metrics are not populated yet.")
        return

    pg_version = status_dict.get("postgresVersion", "N/A")
    total_instances = status_dict.get("instances", 0)
    os_arch = f"{status_dict.get('os', '')} / {status_dict.get('arch', '')}".strip(" /")

    conditions = status_dict.get("conditions", [])
    is_bootstrapped = any(c.get("type") == "Bootstrapped" and c.get("status") == "True" for c in conditions)
    is_failed = any(c.get("type") == "Failed" and c.get("status") == "True" for c in conditions)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        if is_failed:
            st.error("Status: Failed")
        elif is_bootstrapped:
            st.success("Status: Ready")
        else:
            st.info("Status: Initializing")
    with m2:
        st.metric("PostgreSQL Version", pg_version)
    with m3:
        st.metric("Total Instances", total_instances)
    with m4:
        st.metric("OS / Arch", os_arch if os_arch else "N/A")

    st.markdown("---")

    st.markdown("#### 🖥️ Pod Instances & Roles")
    pod_statuses = status_dict.get("podStatuses", [])
    if pod_statuses:
        pods_data = []
        for pod in pod_statuses:
            role = "👑 Primary" if pod.get("primary") else "🔁 Replica"
            restart_needed = "⚠️ Yes" if pod.get("pendingRestart") else "✅ No"
            pods_data.append({
                "Pod Name": pod.get("name"),
                "Role": role,
                "Node Name": pod.get("nodeName"),
                "Pending Restart": restart_needed,
                "Replication Group": pod.get("replicationGroup")
            })
        st.dataframe(pd.DataFrame(pods_data), width="stretch", hide_index=True)
    else:
        st.info("No active pod instances reported yet.")

    st.markdown("#### 📋 Cluster Conditions")
    if conditions:
        cond_data = []
        for c in conditions:
            cond_data.append({
                "Condition": c.get("type"),
                "Status": "✅ True" if c.get("status") == "True" else "❌ False",
                "Reason": c.get("reason"),
                "Last Transition": c.get("lastTransitionTime")
            })
        st.dataframe(pd.DataFrame(cond_data), width="stretch", hide_index=True)

    with st.expander("🔍 View Raw Status JSON"):
        st.json(status_dict)

if st.button("Check Status"):
    if check_name:
        res = requests.get(f"{API_URL}/{check_ns}/{check_name}")
        if res.status_code == 200:
            status_data = res.json().get("status", {})
            render_cluster_dashboard(status_data, check_name, check_ns)
        else:
            st.warning("Cluster not found or still initializing.")
    else:
        st.warning("Please enter a Cluster Name.")