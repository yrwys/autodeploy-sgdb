import os
import streamlit as st
import requests
import pandas as pd

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/v1/databases")

st.set_page_config(page_title="StackGres Cluster Portal", page_icon="🛢️")
st.markdown("<h1 style='text-align: center;'>StackGres Cluster Portal</h1>", unsafe_allow_html=True)
st.write("")


with st.form("deploy_db"):
    col1, col2 = st.columns(2)
    with col1:
        cluster_name = st.text_input("Cluster Name", placeholder="tenant-db")
        postgres_version = st.selectbox("PostgreSQL Version", ["Select PostgreSQL Version", "16", "15", "14", "13"], index=0)
        cpu_alloc = st.selectbox("CPU per Instance", ["Select CPU Allocation", "2000m", "3000m", "4000m", "6000m"], index=0)
        storage = st.text_input("Storage Size", placeholder="10Gi")
    
    with col2:
        namespace = st.text_input("Namespace", placeholder="default")
        instances = st.slider("Total Instances (includes 1 Primary)", min_value=1, max_value=5, value=2)
        memory_alloc = st.selectbox("Memory per Instance", ["Select Memory Allocation", "3Gi", "4Gi", "6Gi", "8Gi"], index=0)
        storage_class = st.selectbox("Storage Class", ["Select Storage Class", "longhorn-class-a", "longhorn-class-b", "longhorn-class-c", "longhorn-class-d"], index=0)
    
    submitted = st.form_submit_button("Deploy Cluster")


if submitted:
    errors = []
    final_cluster_name = cluster_name.strip() if cluster_name.strip() else "tenant-db"
    final_namespace = namespace.strip() if namespace.strip() else "default"
    final_storage = storage.strip() if storage.strip() else "10Gi"

    if postgres_version.startswith("Select"):
        errors.append("Please select a valid PostgreSQL Version.")
    if cpu_alloc.startswith("Select"):
        errors.append("Please select a valid CPU Allocation.")
    if memory_alloc.startswith("Select"):
        errors.append("Please select a valid Memory Allocation.")

    if errors:
        for err in errors:
            st.error(err)
    else:
        clean_cpu = cpu_alloc.split()[0]
        selected_sc = None if storage_class.startswith("Select") else storage_class

        payload = {
            "cluster_name": final_cluster_name,
            "namespace": final_namespace,
            "instances": instances,
            "postgres_version": postgres_version,
            "storage_size": final_storage,
            "storage_class": selected_sc,
            "cpu_request": clean_cpu,
            "memory_request": memory_alloc
        }
        
        with st.spinner(f"Provisioning {final_cluster_name}..."):
            try:
                response = requests.post(API_URL, json=payload)
                
                if response.status_code == 201:
                    st.success("Cluster provisioning initiated successfully!")
                    data = response.json()
                    st.code(f"Primary Endpoint: {data['endpoints']['primary_rw']}")
                else:
                    st.error(f"Error: {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to API: {e}")


st.divider()
st.subheader("Check Cluster Status")
check_col1, check_col2 = st.columns(2)
with check_col1:
    check_name = st.text_input("Cluster Name to check", placeholder="tenant-db")
with check_col2:
    check_ns = st.text_input("Namespace to check", placeholder="default")


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
        st.dataframe(pd.DataFrame(pods_data), width='stretch', hide_index=True)
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
        st.dataframe(pd.DataFrame(cond_data), width='stretch', hide_index=True)

    with st.expander("🔍 View Raw Status JSON"):
        st.json(status_dict)


if st.button("Check Status"):
    final_check_name = check_name.strip()
    final_check_ns = check_ns.strip() if check_ns.strip() else "default"

    if final_check_name:
        try:
            res = requests.get(f"{API_URL}/{final_check_ns}/{final_check_name}")
            if res.status_code == 200:
                status_data = res.json().get("status", {})
                render_cluster_dashboard(status_data, final_check_name, final_check_ns)
            else:
                st.warning("Cluster not found or still initializing.")
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to connect to API: {e}")
    else:
        st.warning("Please enter a Cluster Name.")